########################################
# Filename: presence_detector.py
# Student:  Juan Yin, j9yin@ucsd.edu
# Project:  Study Buddy Pupper -- Final Project (CSE 276B)
#
# Description:
#   Study Buddy Pupper -- CV User-Presence Detection node. This node decides, on
#   every camera frame, whether a person is present and publishes that state so
#   the behavior controller (study_buddy_fsm) can react. It is the first of the
#   two computer-vision nodes I built; the second is phone_detector.py, and both
#   share the same OAK-D RGB camera. The per-frame data flow is:
#     /oak/rgb/image_raw  ->  person detection (anywhere in frame)
#                         ->  temporal smoothing (grace)  ->  ROS topics
#
#   Publishes (consumed unchanged by study_buddy_fsm):
#     study_zone/present        (std_msgs/Bool)    True  = a person is present
#     study_zone/seconds_away   (std_msgs/Float32) seconds since last seen
#
#   Camera source: subscribes to the OAK-D RGB topic from Lab 1
#   (/oak/rgb/image_raw) and converts each ROS Image to OpenCV with cv_bridge --
#   the same pattern as Lab 1's echo_camera.py.
#
#   Detection rule: "person anywhere in the frame" -- if a person is detected at
#   all, the user is present. The backend is swappable from config.py:
#     'pose' = MediaPipe Pose (default)   'hog' = OpenCV HOG people detector
#   so the node still runs if MediaPipe will not install on the Pi.
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
#     # 3. Run the node (registered as the `detector` console script):
#     ros2 run study_zone_detector detector
#
#     # 4. (Optional) confirm the published topics from another terminal:
#     ros2 topic echo /study_zone/present
#     ros2 topic echo /study_zone/seconds_away
#
# Acknowledgements: camera subscription / cv_bridge pattern from Prof. Riek's
#   Lab 1 echo_camera.py; MediaPipe Pose API from google-ai-edge/mediapipe.
########################################

import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from std_msgs.msg import Bool, Float32
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

import cv2

from study_zone_detector import config as cfg

# Pin OpenCV's thread pool before any cv2 work so this node does not fight the
# other heavy processes (MediaPipe, Whisper) for the Pi's 4 cores. See config.
cv2.setNumThreads(cfg.OPENCV_THREADS)


# ---------------- Detection backends ----------------
# Each backend exposes detect(frame_bgr) -> (found: bool, box | None), where box
# is (x1, y1, x2, y2) in pixels for the debug window (or None).

class PoseDetector:
    """MediaPipe Pose. A person is 'found' when enough torso landmarks are
    visible. Single-person, CPU-friendly."""

    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24

    def __init__(self):
        """
        Name:    __init__(self)
        Purpose: Build the MediaPipe Pose estimator at the speed/accuracy settings
                 from config.py (POSE_MODEL_COMPLEXITY = 0 is the fastest, which is
                 what the Raspberry Pi needs). MediaPipe is imported lazily here so
                 that selecting the 'hog' backend never requires it to be installed.
        @input   self: the detector instance.
        @return  None.
        """
        import mediapipe as mp
        self.pose = mp.solutions.pose.Pose(
            min_detection_confidence=cfg.MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=cfg.MIN_TRACKING_CONFIDENCE,
            model_complexity=cfg.POSE_MODEL_COMPLEXITY,
        )

    def detect(self, frame_bgr):
        """
        Name:    detect(self, frame_bgr)
        Purpose: Run MediaPipe Pose on one frame and decide whether a person is
                 present. A person counts as found when at least
                 MIN_VISIBLE_LANDMARKS of the four torso landmarks (the two
                 shoulders and two hips) are visible above 0.5 confidence, which
                 keeps the signal robust to slouching and partial framing.
        @input   frame_bgr: the (possibly downscaled) BGR frame to analyze.
        @return  A 2-tuple (found, box):
                   found -- bool, True if a person was detected.
                   box   -- (x1, y1, x2, y2) torso bounding box in this frame's
                            pixels for the debug window, or None.
        """
        h, w = frame_bgr.shape[:2]
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb)
        if not results.pose_landmarks:
            return False, None

        lm = results.pose_landmarks.landmark
        xs, ys = [], []
        for idx in (self.LEFT_SHOULDER, self.RIGHT_SHOULDER,
                    self.LEFT_HIP, self.RIGHT_HIP):
            p = lm[idx]
            if p.visibility > 0.5:
                xs.append(p.x)
                ys.append(p.y)

        if len(xs) < cfg.MIN_VISIBLE_LANDMARKS:
            return False, None

        box = (int(min(xs) * w), int(min(ys) * h),
               int(max(xs) * w), int(max(ys) * h))
        return True, box

    def close(self):
        """
        Name:    close(self)
        Purpose: Release the MediaPipe Pose graph and its native resources when
                 the node shuts down.
        @input   self: the detector instance.
        @return  None.
        """
        self.pose.close()


class HogDetector:
    """OpenCV HOG + SVM people detector. No extra dependency beyond opencv.
    Less accurate than Pose but a reliable fallback on the Pi."""

    def __init__(self):
        """
        Name:    __init__(self)
        Purpose: Build OpenCV's HOG + SVM people detector and load the default
                 pre-trained pedestrian model. This is the fallback backend that
                 needs no dependency beyond opencv, used when MediaPipe will not
                 install on the Pi.
        @input   self: the detector instance.
        @return  None.
        """
        self.hog = cv2.HOGDescriptor()
        self.hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    def detect(self, frame_bgr):
        """
        Name:    detect(self, frame_bgr)
        Purpose: Run the HOG people detector on one frame and report whether a
                 person is present, returning the first detected box.
        @input   frame_bgr: the (possibly downscaled) BGR frame to analyze.
        @return  A 2-tuple (found, box):
                   found -- bool, True if at least one person box was detected.
                   box   -- (x1, y1, x2, y2) of the first detection in this
                            frame's pixels, or None.
        """
        rects, _ = self.hog.detectMultiScale(
            frame_bgr, winStride=(8, 8), padding=(8, 8), scale=1.05)
        if len(rects) == 0:
            return False, None
        x, y, w, h = rects[0]
        return True, (x, y, x + w, y + h)

    def close(self):
        """
        Name:    close(self)
        Purpose: Match the PoseDetector interface. HOG holds no native resources,
                 so there is nothing to release.
        @input   self: the detector instance.
        @return  None.
        """
        pass


def make_detector():
    """
    Name:    make_detector()
    Purpose: Factory that returns the detection backend selected in config.py, so
             the rest of the node never needs to know which one is active.
    @input   None (reads cfg.DETECTOR_BACKEND).
    @return  A PoseDetector or HogDetector instance.
    @raises  ValueError if DETECTOR_BACKEND is not 'pose' or 'hog'.
    """
    if cfg.DETECTOR_BACKEND == 'pose':
        return PoseDetector()
    if cfg.DETECTOR_BACKEND == 'hog':
        return HogDetector()
    raise ValueError(
        f"Unknown DETECTOR_BACKEND {cfg.DETECTOR_BACKEND!r}; use 'pose' or 'hog'.")


# ---------------- ROS node ----------------
class StudyZoneDetector(Node):

    def __init__(self):
        """
        Name:    __init__(self)
        Purpose: Construct the StudyZoneDetector ROS 2 node. Creates the two
                 output publishers, the cv_bridge converter, the chosen detection
                 backend, the temporal-smoothing state, and the subscription to
                 the camera topic.
        @input   self: the node instance being constructed.
        @return  None. Leaves a fully wired ROS 2 node ready for rclpy.spin().
        """
        super().__init__('study_zone_detector')

        # Publishers consumed by the behavior controller (study_buddy_fsm).
        self.present_pub = self.create_publisher(Bool, cfg.TOPIC_PRESENT, 10)
        self.away_pub = self.create_publisher(Float32, cfg.TOPIC_SECONDS_AWAY, 10)

        # ROS Image -> OpenCV bridge (same as Lab 1 echo_camera.py).
        self.bridge = CvBridge()
        self.detector = make_detector()

        # Temporal smoothing. Assume present at startup so we do not begin with a
        # spurious "left".
        self.last_present = time.time()

        # Throttle: pose is expensive, so we only run detection on 1 in N frames.
        self._frame_count = 0

        # Frames arrive as messages on the camera topic; react to each one.
        # Sensor-data QoS = keep-last depth 1, best-effort: when the Pi falls
        # behind, ROS DROPS stale frames instead of queuing them, so we always
        # process the freshest frame and never build a backlog that snowballs
        # into a freeze. (Was depth 10, which buffered the backlog.)
        self.create_subscription(
            Image, cfg.CAMERA_TOPIC, self.on_image, qos_profile_sensor_data)

        self.get_logger().info(
            f'study_zone_detector started (backend={cfg.DETECTOR_BACKEND}, '
            f'topic={cfg.CAMERA_TOPIC}). Waiting for frames...')

    def on_image(self, msg):
        """
        Name:    on_image(self, msg)
        Purpose: Per-frame camera callback. Throttles the frame rate, converts the
                 ROS image to OpenCV, downscales it, runs the active detector,
                 applies the AWAY_SECONDS smoothing to turn the raw detection into
                 a stable present/away signal, and publishes that signal plus the
                 seconds-away payload for the FSM.
        @input   msg: sensor_msgs/Image, one raw RGB frame from the OAK-D camera.
        @return  None. Publishes on study_zone/present and study_zone/seconds_away
                 as a side effect.
        """
        # Throttle: skip most frames so pose runs ~PROCESS_EVERY_N times slower.
        # Running MediaPipe on every frame saturates the Pi and freezes it.
        self._frame_count += 1
        if cfg.PROCESS_EVERY_N > 1 and (self._frame_count % cfg.PROCESS_EVERY_N) != 0:
            return

        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:
            self.get_logger().warn(f'cv_bridge conversion failed: {e}')
            return

        # Downscale before detection -- pose/HOG are far faster on a smaller image
        # and "is a person present" is unaffected. box is in this frame's coords.
        small = frame
        if cfg.DETECT_WIDTH and frame.shape[1] > cfg.DETECT_WIDTH:
            scale = cfg.DETECT_WIDTH / frame.shape[1]
            small = cv2.resize(
                frame, (cfg.DETECT_WIDTH, int(frame.shape[0] * scale)))

        found, box = self.detector.detect(small)

        now = time.time()
        if found:
            self.last_present = now
        seconds_away = now - self.last_present
        present = seconds_away < cfg.AWAY_SECONDS

        # Publish for the behavior controller.
        self.present_pub.publish(Bool(data=present))
        self.away_pub.publish(Float32(data=float(seconds_away)))

        if cfg.SHOW_DEBUG_WINDOW:
            # box is in the downscaled frame's coords, so draw on that frame.
            self.draw_debug(small, box, present, seconds_away)

    def draw_debug(self, frame, box, present, seconds_away):
        """
        Name:    draw_debug(self, frame, box, present, seconds_away)
        Purpose: Developer-only visualization (active when SHOW_DEBUG_WINDOW is
                 True). Draws the detected-person box (green when present, orange
                 when away) and the present/away text on the frame and displays it.
                 Not used on the headless robot.
        @input   frame: the BGR frame to draw on and display.
        @input   box: (x1, y1, x2, y2) person bounding box, or None.
        @input   present: bool, the current smoothed presence state.
        @input   seconds_away: float, seconds since the person was last seen.
        @return  None. Renders the debug window as a side effect.
        """
        if box is not None:
            x1, y1, x2, y2 = box
            color = (0, 255, 0) if present else (0, 165, 255)
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

        state = 'PRESENT' if present else 'AWAY'
        cv2.putText(frame, f'{state}  away={seconds_away:0.1f}s',
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    (255, 255, 255), 2)

        cv2.imshow('study_zone_detector', frame)
        cv2.waitKey(1)

    def shutdown(self):
        """
        Name:    shutdown(self)
        Purpose: Clean up on exit -- release the detection backend and close any
                 OpenCV debug windows. Called from main() after rclpy.spin returns.
        @input   self: the node instance.
        @return  None.
        """
        self.detector.close()
        if cfg.SHOW_DEBUG_WINDOW:
            cv2.destroyAllWindows()


def main():
    """
    Name:    main()
    Purpose: ROS 2 entry point for the `detector` console script. Initializes
             rclpy, constructs the StudyZoneDetector node, spins it until
             interrupted, then shuts the node and rclpy down cleanly.
    @input   None.
    @return  None.
    """
    rclpy.init()
    node = StudyZoneDetector()
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
