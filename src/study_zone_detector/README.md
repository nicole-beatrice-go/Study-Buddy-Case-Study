```bash
Build (on the Pi)

  pip install opencv-python mediapipe        # mediapipe only needed for 'pose'
  cd ~/ros2_ws
  colcon build --packages-select study_zone_detector seat_presence_detector
  source install/setup.bash

  # Stage 1 — verify the CV works

  # Terminal 1 — launch the camera (leave it running):
  ros2 launch depthai_ros_driver camera.launch.py   # wait for "Camera ready!"
  # Terminal 2 — run the detector:
  ros2 run study_zone_detector detector
  # A study_zone_detector window pops up. Stand in front of the camera → green box + PRESENT. Step out → after 2 s it flips to AWAY.

  # Terminal 3 — confirm the published signal (this is what the FSM will see):
  ros2 topic echo /study_zone/present
  # Should read data: true when you're in frame, data: false when you leave. ✅ CV verified.

  #If MediaPipe fails to install on the Pi, set DETECTOR_BACKEND = 'hog' in config.py, rebuild, and retry — no MediaPipe needed.

  # Stage 2 — verify the FSM on top of it

  # Keep the camera (T1) and detector (T2) running, then:
  ros2 run seat_presence_detector study_buddy
#   Now walk away from the camera and watch the FSM log:
#   - gone > 2 s → STUDYING → COUNTDOWN (timer ticks down from COUNTDOWN_SECONDS)
#   - come back before 0 → → STUDYING (no penalty)
#   - stay away past the countdown → → SLEEPING
#   - return → → STUDYING_SAD
  
#   💡 Set COUNTDOWN_SECONDS = 10.0 in seat_presence_detector/config.py for fast testing so you're not waiting 2 minutes.

#   You can still fake the detector entirely (no camera) with ros2 topic pub --once /study_zone/present std_msgs/msg/Bool "{data: false}" if you want to test FSM logic away from the robot.
```

# Now with the study_buddy.launch.py:

```bash

  # How to run the FSM now

  Build everything:
  cd ~/ros2_ws
  colcon build --packages-select study_zone_detector study_buddy_behavior # adding all 
  source install/setup.bash
  
  # Option 1 — one command (the launch file):
  ros2 launch study_buddy_behavior study_buddy.launch.py
  # This starts the camera + detector + FSM together. If you'd rather start the camera yourself (or depthai_ros_driver isn't found), it prints a warning and still launches the detector + FSM — or pass:
  ros2 launch study_buddy_behavior study_buddy.launch.py start_camera:=false

  # Option 2 — run nodes individually (good while debugging, so each has its own terminal/logs):
  ros2 launch depthai_ros_driver camera.launch.py   # T1: camera (wait for "Camera ready!")
  ros2 run study_zone_detector detector             # T2: CV detector
  ros2 run study_buddy_behavior study_buddy         # T3: FSM

```

### For phone detection
Resolving the accuracy worry

1. Only act on positive evidence (enrollment).
The detector won't nag just because it can't see a card. It first has to see the card sitting at rest ("enroll"). Only then does the card leaving its resting spot
count as "picked up." Consequences:
- No card placed / card never detected → never distracted (timer just runs normally).
- This means a lighting failure where the card is simply hard to see does not trigger a false distraction the same way — the logic keys off "card was here, now it
moved," not "I see nothing."

2. Three independent ways to un-pause (so it's never stuck):
- Phone detected back (primary), with a resume bias — easier/faster to declare "back" than "gone" (asymmetric grace), so we err toward resuming.
- Tap to resume — a touch on the pad force-resumes the session. Detection totally failed? The user just taps. (Your touch node is already wired — free safety net.)
- Auto-resume cap — if it's been "distracted" longer than DISTRACT_MAX_SECONDS (e.g. 90s) without resolving, the timer resumes anyway. Guarantees no permanent
stuck-pause.

3. Always tell the user why it paused.
On entering DISTRACTED: sad face + speech "I paused your timer — put your phone down, or tap me, to keep going." So a stopped timer is never mysterious.

4. Make the whole thing a one-line toggle.
PAUSE_WHEN_DISTRACTED = True in config. If real-world accuracy turns out poor during testing, flip it to False → the robot then keeps the timer running and only nags
(your "keep running" option) without any code change.

5. Measure accuracy first.
During the lighting sweep, the detector will log every on-desk↔picked-up transition (and the debug window shows the mask). You watch a few real pick-up/put-down
cycles under each lighting condition and see the false-positive/negative rate. Then you decide whether to keep PAUSE_WHEN_DISTRACTED on. The toggle makes that a
5-second decision, not a rewrite.