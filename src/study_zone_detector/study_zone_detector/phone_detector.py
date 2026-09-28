########################################
# Filename: phone_detector.py
# Student:  Juan Yin, j9yin@ucsd.edu
# Project:  Study Buddy Pupper -- Final Project (CSE 276B)
#
# Description:
#   Study Buddy Pupper -- CV Phone-Distraction Detection node. This node watches
#   a COLOR CARD placed on the user's phone and decides whether the phone is
#   resting on the desk (good) or has been picked up (distraction), so the
#   behavior FSM (study_buddy_fsm) can nag the user to lock back in.
#
#   This is the second of the two computer-vision nodes I built; the first is
#   presence_detector.py, and both share the same OAK-D RGB camera. The per-frame
#   data flow is:
#     /oak/rgb/image_raw  ->  HSV color-card detection  ->  enrollment + grace
#                         ->  ROS topics
#
#   Publishes (consumed by study_buddy_fsm):
#     study_buddy/phone_on_desk      (std_msgs/Bool)    True = phone resting on desk
#     study_buddy/phone_away_seconds (std_msgs/Float32) seconds since it left the desk
#
#   Key idea (robustness): the node only acts on POSITIVE evidence. The card must
#   first be seen at rest ("enrolled"); only then does it LEAVING count as
#   "picked up". If no card is ever seen, we never report a distraction.
#
# How to use:
#   Usage:
#     # 1. Launch the OAK-D camera (RGB only); wait for "Camera ready!":
#     ros2 launch depthai_ros_driver camera.launch.py params_file:=/home/ubuntu/oak_rgb.yaml
#
#     # 2. Build and source the workspace:
#     cd ~/ros2_ws && colcon build --packages-select study_zone_detector
#     source install/setup.bash
#
#     # 3. (Once per location) tune the card color for the room's lighting:
#     #      set PHONE_CALIBRATE = True in config.py, run the node, read the
#     #      suggested CARD_LOWER / CARD_UPPER from the terminal, paste them into
#     #      config.py, then set PHONE_CALIBRATE = False.
#
#     # 4. Run the node:
#     ros2 run study_zone_detector phone
#
#     # 5. (Optional) confirm the published topics from another terminal:
#     ros2 topic echo /study_buddy/phone_on_desk
#     ros2 topic echo /study_buddy/phone_away_seconds
#
# Build status:
#   [DONE]  Step 1 -- find_card() + draw_debug() + headless logging
#   [DONE]  Step 2 -- calibrate()
#   [DONE]  Step 3 -- publish phone_on_desk (raw detection)
#   [DONE]  Step 4 -- enrollment / resting spot
#   [DONE]  Step 5 -- asymmetric grace + phone_away_seconds
#
# Acknowledgements: HSV color-mask pattern adapted from Lab 1
#   publisher_member_function.py; camera subscription / cv_bridge pattern from
#   Prof. Riek's Lab 1 echo_camera.py.
########################################

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, Float32
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

import cv2
import numpy as np

from study_zone_detector import config as cfg

# Pin OpenCV's thread pool before any cv2 work so this node does not fight the
# other heavy processes (MediaPipe, Whisper) for the Pi's 4 cores. See config.
cv2.setNumThreads(cfg.OPENCV_THREADS)


class PhoneDetector(Node):

    def __init__(self):
        """
        Name:    __init__(self)
        Purpose: Construct the PhoneDetector ROS 2 node. Creates the two output
                 publishers, the cv_bridge converter, every piece of tracking and
                 decision state used by the enrollment and grace logic, and the
                 subscription to the camera topic.
        @input   self: the node instance being constructed.
        @return  None. Leaves a fully wired ROS 2 node ready for rclpy.spin().
        """
        super().__init__('phone_detector')

        # --- publishers (wired in Step 3) ---
        self.on_desk_pub = self.create_publisher(Bool, cfg.TOPIC_PHONE_ON_DESK, 10)
        self.away_pub = self.create_publisher(Float32, cfg.TOPIC_PHONE_AWAY_SECONDS, 10)

        self.bridge = CvBridge()

        # --- tracking state (used from Step 4 on) ---
        self.enrolled = False        # have we ever seen the card at rest?
        self.resting = None          # (cx, cy) confirmed resting centroid once enrolled
        self._stable_anchor = None   # (cx, cy) candidate spot we're timing for stability
        self._stable_since = None    # when the card first became stable at the anchor

        # --- Step 5 decision state (asymmetric grace) ---
        self._on_desk = True         # smoothed/published state; assume OK until proven gone
        self.last_on_desk = time.time()   # last time the card was actually at rest
        self._back_since = None      # when the card returned, for the resume grace

        # --- debug / logging helpers ---
        self._last_mask = None       # last binary mask, for the debug window
        self._last_found = None      # last found-state, to log only on change
        self._last_on_desk_log = True  # last published on_desk, to log only on flip
        self._last_calib_log = 0.0   # throttle the calibration log (Step 2)

        # Throttle: the HSV pipeline runs per frame; skip most of them on the Pi.
        self._frame_count = 0

        # Sensor-data QoS = keep-last depth 1, best-effort: when the Pi falls
        # behind, ROS DROPS stale frames instead of queuing them, so we always
        # process the freshest frame and never build a backlog that snowballs
        # into a freeze. (Was depth 10, which buffered the backlog.)
        self.create_subscription(
            Image, cfg.CAMERA_TOPIC, self.on_image, qos_profile_sensor_data)
        self.get_logger().info(
            f'phone_detector started (topic={cfg.CAMERA_TOPIC}, '
            f'calibrate={cfg.PHONE_CALIBRATE}). Waiting for frames...')

    # ---------------- per-frame entry ----------------
    def on_image(self, msg):
        """
        Name:    on_image(self, msg)
        Purpose: Per-frame camera callback and the heart of the node. Throttles
                 the frame rate, converts the ROS image to OpenCV, locates the
                 card (find_card), refreshes the resting-spot enrollment
                 (update_enrollment), decides the smoothed on-desk state
                 (decide_on_desk), publishes that state for the FSM, and logs or
                 draws debug output.
        @input   msg: sensor_msgs/Image, one raw RGB frame from the OAK-D camera.
        @return  None. Publishes on study_buddy/phone_on_desk and
                 study_buddy/phone_away_seconds as a side effect.
        """
        # Throttle: skip most frames so the HSV pipeline runs ~N times slower.
        # (Time-based graces in decide_on_desk are unaffected by the lower rate.)
        self._frame_count += 1
        if (cfg.PHONE_PROCESS_EVERY_N > 1
                and (self._frame_count % cfg.PHONE_PROCESS_EVERY_N) != 0):
            return

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().warn(f'cv_bridge conversion failed: {e}')
            return

        # Step 2: calibration short-circuits normal detection.
        if cfg.PHONE_CALIBRATE:
            self.calibrate(frame)
            return

        # Downscale before the HSV pipeline -- far cheaper, and find_card rescales
        # its result back to full-res coords so AREA_MIN / MOVE_PX / RESTING_RADIUS
        # keep their meaning regardless of PHONE_DETECT_WIDTH.
        small, scale = frame, 1.0
        if cfg.PHONE_DETECT_WIDTH and frame.shape[1] > cfg.PHONE_DETECT_WIDTH:
            scale = cfg.PHONE_DETECT_WIDTH / frame.shape[1]
            small = cv2.resize(
                frame, (cfg.PHONE_DETECT_WIDTH, int(frame.shape[0] * scale)))

        # Step 1: locate the card this frame.
        found, area, centroid, box = self.find_card(small, scale)

        # Headless feedback: log only when the found-state flips (no spam).
        if found != self._last_found:
            self._last_found = found
            if found:
                self.get_logger().info(
                    f'card detected: area={int(area)} at {centroid}')
            else:
                self.get_logger().info('card lost')

        # Step 4: learn / refresh the resting spot (must run before the decision so
        # decide_on_desk() sees the current enrollment / resting centroid).
        self.update_enrollment(found, centroid)

        # Step 5: smooth raw detection into a stable on_desk decision + away time,
        # then publish what the FSM consumes. (Replaces the raw Step 3 publish.)
        on_desk, away_seconds = self.decide_on_desk(found, centroid)
        self.on_desk_pub.publish(Bool(data=bool(on_desk)))
        self.away_pub.publish(Float32(data=float(away_seconds)))

        # Log the smoothed decision only when it flips, so the FSM-facing signal is
        # easy to follow (separate from the raw card detected/lost lines above).
        if on_desk != self._last_on_desk_log:
            self._last_on_desk_log = on_desk
            self.get_logger().info(
                f'phone {"ON desk" if on_desk else "PICKED UP"} '
                f'(away={away_seconds:.1f}s)')

        if cfg.SHOW_DEBUG_WINDOW:
            self.draw_debug(frame, box, found, area)

    # ---------------- Step 1: color-card detection ----------------
    def find_card(self, frame_bgr, scale=1.0):
        """
        Name:    find_card(self, frame_bgr, scale=1.0)
        Purpose: Locate the color card in one frame. Builds an HSV mask
                 (CARD_LOWER..CARD_UPPER), takes the largest contour, rejects it
                 if it is smaller than AREA_MIN, and returns the card's centroid
                 and bounding box. Coordinates and area are rescaled back to
                 FULL-RES units (inv = 1/scale) so AREA_MIN / MOVE_PX /
                 RESTING_RADIUS keep their meaning at any PHONE_DETECT_WIDTH.
        @input   frame_bgr: the (possibly downscaled) BGR frame to search.
        @input   scale: the factor the frame was downscaled by (small / full width).
        @return  A 4-tuple (found, area, centroid, box):
                   found    -- bool, True if a card larger than AREA_MIN was seen.
                   area     -- float, the largest-contour area in full-res pixels.
                   centroid -- (cx, cy) full-res pixel centroid, or None.
                   box      -- (x1, y1, x2, y2) full-res bounding box, or None.
        """
        inv = 1.0 / scale
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array(cfg.CARD_LOWER, dtype=np.uint8)
        upper = np.array(cfg.CARD_UPPER, dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        # Denoise (optional, off by default to save CPU). The card is the LARGEST
        # blob, so max-contour + AREA_MIN already rejects speckle; only enable a
        # single light open if a noisy background creates a bigger false blob.
        if cfg.PHONE_USE_MORPH:
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        self._last_mask = mask

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False, 0.0, None, None

        c = max(contours, key=cv2.contourArea)
        # Contour area scales with the square of the linear downscale factor.
        area = float(cv2.contourArea(c)) * inv * inv
        if area < cfg.AREA_MIN:
            return False, area, None, None

        m = cv2.moments(c)
        if m['m00'] == 0:
            return False, area, None, None
        cx = int(m['m10'] / m['m00'] * inv)
        cy = int(m['m01'] / m['m00'] * inv)
        x, y, w, h = cv2.boundingRect(c)
        return True, area, (cx, cy), (
            int(x * inv), int(y * inv), int((x + w) * inv), int((y + h) * inv))

    # ---------------- Step 2: calibration helper ----------------
    def calibrate(self, frame_bgr):
        """
        Name:    calibrate(self, frame_bgr)
        Purpose: One-time HSV tuning helper (active only while PHONE_CALIBRATE is
                 True). Samples a center ROI of the frame, logs its hue/sat/value
                 statistics about once per second, and prints a ready-to-paste
                 CARD_LOWER / CARD_UPPER suggestion. Place the card inside the
                 on-screen box and read the numbers from the terminal.
        @input   frame_bgr: the current BGR frame to sample the center ROI from.
        @return  None. Logs the suggested HSV bounds (and draws the ROI box if
                 SHOW_DEBUG_WINDOW is True) as a side effect.
        """
        h, w = frame_bgr.shape[:2]
        rw, rh = int(w * cfg.CALIB_ROI_FRAC), int(h * cfg.CALIB_ROI_FRAC)
        cx, cy = w // 2, h // 2
        x1, y1 = cx - rw // 2, cy - rh // 2
        x2, y2 = cx + rw // 2, cy + rh // 2

        roi = frame_bgr[y1:y2, x1:x2]
        if roi.size == 0:
            return
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        hh, ss, vv = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]

        # Throttle: on_image runs ~30x/sec; only log once per second.
        now = time.time()
        if now - self._last_calib_log >= 1.0:
            self._last_calib_log = now
            h_med = int(np.median(hh))
            # Suggested range: tight hue band around the median; S/V floored at
            # the 10th percentile (rejects the dullest pixels), open to 255.
            h_lo = max(0, h_med - cfg.CALIB_H_MARGIN)
            h_hi = min(179, h_med + cfg.CALIB_H_MARGIN)
            s_lo = int(np.percentile(ss, 10))
            v_lo = int(np.percentile(vv, 10))
            self.get_logger().info(
                f'[CALIB] ROI HSV  '
                f'H[min={int(hh.min())} med={h_med} max={int(hh.max())}]  '
                f'S[min={int(ss.min())} med={int(np.median(ss))} max={int(ss.max())}]  '
                f'V[min={int(vv.min())} med={int(np.median(vv))} max={int(vv.max())}]')
            self.get_logger().info(
                f'[CALIB] suggested ->  CARD_LOWER = ({h_lo}, {s_lo}, {v_lo})   '
                f'CARD_UPPER = ({h_hi}, 255, 255)')

        if cfg.SHOW_DEBUG_WINDOW:
            cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(frame_bgr, 'place card in box', (x1, max(y1 - 10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
            cv2.imshow('phone_detector', frame_bgr)
            cv2.waitKey(1)

    # ---------------- Step 4: enrollment / resting spot ----------------
    def update_enrollment(self, found, centroid):
        """
        Name:    update_enrollment(self, found, centroid)
        Purpose: Learn (and refresh) the card's resting spot on the desk. The card
                 must stay within MOVE_PX of one place continuously for
                 REST_STABLE_SEC before it is trusted as "at rest". Once enrolled,
                 self.resting holds the last CONFIRMED resting spot and persists
                 across a pickup, so decide_on_desk still knows where the desk spot
                 was. Moving the card just restarts the stability timer at the new
                 spot; the old resting spot stays until a NEW one is confirmed. The
                 card disappearing only cancels the in-progress timer -- it never
                 erases an existing enrollment.
        @input   found: bool, whether find_card saw a card this frame.
        @input   centroid: (cx, cy) full-res centroid of the card, or None.
        @return  None. Updates self.enrolled / self.resting / the stability-timer
                 fields as a side effect.
        """
        # Card not visible -> it can't be "at rest"; require a fresh stable
        # window when it reappears, but keep any existing enrollment.
        if not found or centroid is None:
            self._stable_anchor = None
            self._stable_since = None
            return

        now = time.time()

        # Start (or restart) a stability window the first frame we have a card.
        if self._stable_anchor is None:
            self._stable_anchor = centroid
            self._stable_since = now
            return

        # How far has it drifted from the spot we're timing?
        dx = centroid[0] - self._stable_anchor[0]
        dy = centroid[1] - self._stable_anchor[1]
        moved = (dx * dx + dy * dy) ** 0.5

        # Drifted too far -> not the same resting spot; restart timing here.
        if moved > cfg.MOVE_PX:
            self._stable_anchor = centroid
            self._stable_since = now
            return

        # Held still long enough -> (re-)confirm this as the resting spot.
        if now - self._stable_since >= cfg.REST_STABLE_SEC:
            newly = not self.enrolled
            moved_spot = self.resting is not None and self.resting != self._stable_anchor
            self.enrolled = True
            self.resting = self._stable_anchor
            if newly:
                self.get_logger().info(f'card enrolled at rest {self.resting}')
            elif moved_spot:
                self.get_logger().info(f'card re-enrolled at {self.resting}')

    # ---------------- Step 5: on-desk decision (asymmetric grace) ----------------
    def decide_on_desk(self, found, centroid):
        """
        Name:    decide_on_desk(self, found, centroid)
        Purpose: Smooth the raw per-frame detection into the stable on-desk signal
                 the FSM consumes, using an ASYMMETRIC debounce: the card must be
                 gone for PICKUP_GRACE before the phone is called "picked up", but
                 only back for RESUME_GRACE before it is called "on desk" again --
                 biasing toward resuming so a brief CV dropout never nags. Enforces
                 the positive-evidence rule: until the card has been enrolled at
                 rest, it reports on_desk=True / away=0, because a phone that was
                 never set down is never a distraction.
        @input   found: bool, whether find_card saw a card this frame.
        @input   centroid: (cx, cy) full-res centroid of the card, or None.
        @return  A 2-tuple (on_desk, away_seconds):
                   on_desk      -- bool, the smoothed published state.
                   away_seconds -- float, seconds since the card was last at rest
                                   (0.0 while on the desk).
        """
        now = time.time()

        # No resting spot learned yet -> nothing to leave; never report distraction.
        if not self.enrolled or self.resting is None:
            self._on_desk = True
            self._back_since = None
            self.last_on_desk = now
            return True, 0.0

        # Is the card present AND near its enrolled resting spot this frame?
        at_rest = found and centroid is not None
        if at_rest:
            dx = centroid[0] - self.resting[0]
            dy = centroid[1] - self.resting[1]
            at_rest = (dx * dx + dy * dy) ** 0.5 <= cfg.RESTING_RADIUS

        if at_rest:
            if self._on_desk:
                # Still on the desk -- keep the away clock pinned to now.
                self.last_on_desk = now
            else:
                # Card is back; require RESUME_GRACE of continuous presence before
                # flipping, so one lucky frame can't declare a false resume.
                if self._back_since is None:
                    self._back_since = now
                if now - self._back_since >= cfg.RESUME_GRACE:
                    self._on_desk = True
                    self._back_since = None
                    self.last_on_desk = now
        else:
            # Card gone/displaced; cancel any resume in progress.
            self._back_since = None
            # Only declare "picked up" after it's been away past the pickup grace.
            if self._on_desk and now - self.last_on_desk >= cfg.PICKUP_GRACE:
                self._on_desk = False

        away_seconds = 0.0 if self._on_desk else (now - self.last_on_desk)
        return self._on_desk, away_seconds

    # ---------------- debug ----------------
    def draw_debug(self, frame, box, found, area):
        """
        Name:    draw_debug(self, frame, box, found, area)
        Purpose: Developer-only visualization (active when SHOW_DEBUG_WINDOW is
                 True). Overlays the card bounding box and the found/area text on
                 the frame and shows the binary mask in a second window, which is
                 what I used for live HSV tuning. Not used on the headless robot.
        @input   frame: the BGR frame to draw on and display.
        @input   box: (x1, y1, x2, y2) card bounding box, or None.
        @input   found: bool, whether a card was detected this frame.
        @input   area: float, the largest-contour area, shown as on-screen text.
        @return  None. Renders the debug windows as a side effect.
        """
        if box is not None:
            x1, y1, x2, y2 = box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        state = 'CARD' if found else 'no card'
        cv2.putText(frame, f'{state}  area={int(area)}',
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 255), 2)

        cv2.imshow('phone_detector', frame)
        if self._last_mask is not None:
            cv2.imshow('phone_detector mask', self._last_mask)
        cv2.waitKey(1)

    def shutdown(self):
        """
        Name:    shutdown(self)
        Purpose: Clean up on exit -- close any OpenCV debug windows that were
                 opened. Called from main() after rclpy.spin returns.
        @input   self: the node instance.
        @return  None.
        """
        if cfg.SHOW_DEBUG_WINDOW:
            cv2.destroyAllWindows()


def main():
    """
    Name:    main()
    Purpose: ROS 2 entry point for the `phone` console script. Initializes rclpy,
             constructs the PhoneDetector node, spins it until interrupted, then
             shuts the node and rclpy down cleanly.
    @input   None.
    @return  None.
    """
    rclpy.init()
    node = PhoneDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
