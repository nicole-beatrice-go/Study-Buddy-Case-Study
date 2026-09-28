########################################
# Filename: config.py
# Student:  Juan Yin, j9yin@ucsd.edu
# Project:  Study Buddy Pupper -- Final Project (CSE 276B)
#
# Description:
#   Single source of tunable parameters for BOTH computer-vision nodes in this
#   package -- presence_detector.py and phone_detector.py. Every magic number
#   (camera topic, detector backend, performance throttles, smoothing/grace
#   windows, ROS topic names, and the phone color-card thresholds) lives here so
#   the system can be retuned on the robot in one place without editing code. The
#   nodes import this file as `cfg` and read these names directly.
#
# How to use:
#   Edit the values below, then rebuild + source and re-run the node:
#     cd ~/ros2_ws && colcon build --packages-select study_zone_detector
#     source install/setup.bash
#   This file defines constants only; it has no functions to call.
########################################

# ---------------- Camera source ----------------
# The OAK-D RGB topic from Lab 1. Launch the camera separately first:
#   ros2 launch depthai_ros_driver camera.launch.py   (wait for "Camera ready!")
# Confirm the exact name on your robot with:  ros2 topic list
CAMERA_TOPIC = '/oak/rgb/image_raw' #/oak/rgb/

# ---------------- Detector backend ----------------
#   'pose' : MediaPipe Pose (default; needs `pip install mediapipe`)
#   'hog'  : OpenCV HOG people detector (no extra deps; use if MediaPipe won't
#            install on the Pi). Less accurate but always available.
DETECTOR_BACKEND = 'pose'

# ---------------- Detection (MediaPipe 'pose' backend) ----------------
MIN_DETECTION_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5
MIN_VISIBLE_LANDMARKS = 2      # need >=2 of (shoulders, hips) visible to trust it
POSE_MODEL_COMPLEXITY = 0      # 0 = fastest (best for the Pi), 1/2 = more accurate

# ---------------- Performance throttle (Raspberry Pi) ----------------
# MediaPipe pose is expensive; running it on EVERY camera frame (~30 fps) at full
# resolution saturates the Pi's CPU and can freeze the whole system (drops SSH).
# Run detection on only 1 in PROCESS_EVERY_N frames and downscale to DETECT_WIDTH
# px first. Presence ("is a person there") is unaffected by the lower rate/res.
# These apply to presence_detector only; the phone HSV check is already cheap.
PROCESS_EVERY_N = 2            # the OAK already publishes ~5 fps, so 1-in-2 -> ~2.5
                              # checks/sec (10 was tuned for a 30fps source and made
                              # presence update only ~0.5 Hz -- too slow vs AWAY_SECONDS)
DETECT_WIDTH = 320            # downscale width before detection; 0 = full resolution
                              # (320 still detects "is a person there"; lower = lighter CPU)

# Limit OpenCV's internal thread pool. On the 4-core Pi, OpenCV + MediaPipe +
# Whisper all spawning threads thrash the cores against each other; pinning each
# CV node to 1 OpenCV thread reduces context-switch contention under load.
# Both detector nodes call cv2.setNumThreads(OPENCV_THREADS) at startup.
OPENCV_THREADS = 1

# ---------------- Temporal smoothing (grace) ----------------
# A person must be UNSEEN continuously for longer than this before we report
# "away". Keep it SHORT -- it only smooths frame-to-frame CV flicker (a frame
# where detection briefly drops). The meaningful "are you coming back?" wait is
# the 2-minute countdown in study_buddy_fsm, NOT here.
AWAY_SECONDS = 2.0

# ---------------- ROS topics ----------------
# Consumed unchanged by study_buddy_fsm. Keep them in sync with the FSM's config.
TOPIC_PRESENT = 'study_zone/present'            # std_msgs/Bool    True = present
TOPIC_SECONDS_AWAY = 'study_zone/seconds_away'  # std_msgs/Float32 seconds since seen

# ---------------- Debug ----------------
# Shows a window with the detected-person box and the current state. Great for
# verifying the CV works. Set to False when running headless on the Pupper.
# (Reused by BOTH presence_detector and phone_detector.)
SHOW_DEBUG_WINDOW = False # for testing

# ================= Phone-distraction (color card) detection =================
# phone_detector.py watches a COLOR CARD placed on the user's phone and reports
# whether the phone is resting on the desk or has been picked up. Reuses
# CAMERA_TOPIC and SHOW_DEBUG_WINDOW above.

# ---------------- ROS topics (consumed by study_buddy_fsm) ----------------
TOPIC_PHONE_ON_DESK = 'study_buddy/phone_on_desk'           # std_msgs/Bool    True = on desk
TOPIC_PHONE_AWAY_SECONDS = 'study_buddy/phone_away_seconds' # std_msgs/Float32 secs since it left

# ---------------- Calibration ----------------
# True: do NOT detect; instead sample a center ROI each frame and log its HSV so
# you can set CARD_LOWER/UPPER for your lighting. Set back to False to run normally.
PHONE_CALIBRATE = False
CALIB_ROI_FRAC = 0.15          # size of the center sampling box (fraction of frame)
CALIB_H_MARGIN = 10            # +/- hue spread around the card's median, for the suggestion

# ---------------- Card color (HSV) ----------------
# OpenCV HSV ranges: H in 0..179, S/V in 0..255. Set for a NEON GREEN card --
# neon is very saturated/bright, so the S/V minimums are raised to reject dull
# greens (plants, walls). Tune in Step 2 using PHONE_CALIBRATE.
CARD_LOWER = (35, 120, 140)    # neon green (vivid, bright)
CARD_UPPER = (60, 255, 255)

# ---------------- Performance throttle (phone_detector) ----------------
# The HSV pipeline (cvtColor + inRange + morphology + findContours) runs per
# frame; at full res / 30 fps it is NOT free. Throttle + downscale like the
# presence node. find_card rescales area/centroid back to full-res coords, so the
# thresholds below (AREA_MIN, MOVE_PX, RESTING_RADIUS) keep their meaning at any
# PHONE_DETECT_WIDTH -- you do NOT need to retune them after changing the width.
PHONE_PROCESS_EVERY_N = 4      # process 1 frame in N (~30fps / 4 = ~7 checks/sec)
PHONE_DETECT_WIDTH = 320       # downscale width before HSV detection; 0 = full res

# Morphology (open+close) cleans the mask but costs CPU every frame. The neon card
# is the LARGEST blob, so max-contour + AREA_MIN already rejects speckle without
# it. Leave False for the lightest pipeline; set True only if a noisy background
# produces a bigger false blob than the card. (When True it's a single 3x3 open.)
PHONE_USE_MORPH = False

# ---------------- Detection thresholds ----------------
AREA_MIN = 1500                # min card pixels (largest contour area) to count as "seen"

# ---------------- Enrollment / resting spot (Step 4) ----------------
# The card must sit within MOVE_PX of one place for REST_STABLE_SEC before we
# trust it as the phone's "resting spot" on the desk. Only after enrollment does
# the card leaving count as "picked up" (Step 5) -- a phone that was never set
# down never triggers a false distraction.
MOVE_PX = 40                   # px the centroid may wander and still count as "still"
REST_STABLE_SEC = 2.0          # how long it must stay put to enroll as at-rest

# ---------------- On-desk decision / grace (Step 5) ----------------
# Asymmetric debounce on the raw detection before phone_on_desk is published:
#   - card must be GONE for PICKUP_GRACE before we call the phone "picked up"
#     (so a one-frame CV dropout never triggers a false distraction)
#   - card need only be BACK for RESUME_GRACE before we call it "on desk" again
#     (bias toward resuming -- forgive quickly when the user refocuses)
# RESTING_RADIUS: how far (px) the card may sit from its enrolled resting spot and
# still count as on the desk; beyond it (or gone) starts the pickup grace.
PICKUP_GRACE = 2.0             # s the card must be away before -> picked up
RESUME_GRACE = 0.3            # s the card must be back before -> on desk
RESTING_RADIUS = 100          # px tolerance around the enrolled resting spot
