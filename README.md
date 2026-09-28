# Study-Buddy
Study buddy robot

```mermaid
stateDiagram-v2
    direction TB

    state StudyBuddy {

        %% ---- Region 1: Presence / behavior FSM ----
        [*] --> START
        START: START · happy · waiting for tap
        STUDYING: STUDYING · present · session running
        COUNTDOWN: COUNTDOWN · worried · session PAUSED
        SLEEPING: SLEEPING · sleepy · points docked once
        STUDYING_SAD: STUDYING_SAD · sad · session resumed

        START --> STUDYING: tap AND present / start_study
        STUDYING --> COUNTDOWN: leaves (phase != break) / pause
        STUDYING --> START: break_over
        COUNTDOWN --> STUDYING: returns / resume
        COUNTDOWN --> SLEEPING: grace = 0
        SLEEPING --> STUDYING_SAD: present
        SLEEPING --> SLEEPING: wake/tap, no one there (stir)
        STUDYING_SAD --> STUDYING: SAD_RECOVER elapsed
        STUDYING_SAD --> COUNTDOWN: leaves again

        --

        %% ---- Region 2: Pomodoro session phase ----
        [*] --> idle
        idle: idle · mood idle
        study: study · STUDY_MIN
        break: break · BREAK_MIN · mood happy

        idle --> study: start_study (tap+present)
        study --> break: time=0 / study_complete +reward
        break --> idle: time=0 / break_over
        study --> study: voice PAUSE/RESUME
        break --> break: voice PAUSE/RESUME
    }

    note right of StudyBuddy
        VOICE (study_buddy_speech)
        mic - Whisper - intents.parse()
        published on study_buddy/voice_intent:
        PAUSE  -> session.pause()   (no state change)
        RESUME -> session.resume()  (+ study_buddy/wake)
        ADD_TODO / UNKNOWN -> FSM ignores
        wake only stirs SLEEPING; never transitions.
        Voice acts on the SESSION region only.
    end note
```


setup.py will ship them on rebuild — glob('images/*.jpg') now also matches *_RZ.jpg, so they'll get installed into share/. Harmless (just duplicates), but if you'd rather not, you can exclude them — though that's optional and not worth bothering with unless it annoys you.
Neither affects functionality. The resized files persist across runs now, and the node only ever passes the mood images (happy.jpg/sad.jpg/neutral.jpg) into _resized_path, never the _RZ files, so there's no double-resize.
### Rebuild and check:
```bash
  cd ~/ros2_ws && colcon build --packages-select study_buddy_behavior && source install/setup.bash
  # T1
  ros2 run study_buddy_behavior expression
  # T2
  cd ~/ros2_ws && source install/setup.bash && ros2 topic pub --once study_buddy/mood std_msgs/msg/String "{data: happy}"
  # T3
  ls ~/ros2_ws/src/Study-Buddy/src/study_buddy_behavior/images/   # should show happy_RZ.jpg after first happy mood
```