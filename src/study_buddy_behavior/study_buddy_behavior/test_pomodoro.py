########################################################################
# Filename: test_pomodoro.py
# Student:  Nicole Go, nbgo@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Pomodoro Timer Test (Final Project)
#
# Study Buddy Pupper -- PomodoroTimer validation utility.
#
# Purpose:
#   Test that the PomodoroTimer class
#   correctly manages study sessions, break sessions, pause/resume
#
# Why this exists:
#   The PomodoroTimer is is used for the Study Buddy to track sessions and update the FSM
#   It tracks flags on if it is paused and allows the user to pause
#   It also tracks how much time is left
#
#   Testing the timer separately makes it easier to debug timing logic,
#   reward calculations, and pause/resume behavior without involving ROS,
#   sensors, or robot movement.
#
# Tests performed:
#   1. Verify initial timer state
#   2. Start a study session
#   3. Confirm countdown progression
#   4. Verify pause functionality stops the countdown
#   5. Verify resume functionality restarts the countdown
#   6. Force study completion and check:
#        - study_complete event returned
#        - transition into break phase
#        - completion reward applied
#   7. Force break completion and check:
#        - break_over event returned
#        - transition back to idle phase
#
# Usage:
#   python3 test_pomodoro.py
#
# Expected outcome:
#   The console displays timer status throughout the test and confirms
#   correct state transitions between idle, study, and break phases.
#
# Dependencies:
#   study_buddy_behavior.pomodoro.PomodoroTimer
########################################################################

import time

from study_buddy_behavior.pomodoro import PomodoroTimer


def print_status(timer):
    print(
        f"phase={timer.phase} | "
        f"paused={timer.paused} | "
        f"time_left={timer.time_left():.1f}s | "
        f"points={timer.points.points}"
    )


def main():
    timer = PomodoroTimer()
    #test start
    print("\n=== Initial State ===")
    print_status(timer)

    print("\n=== Start Study ===")
    timer.start_study()
    print_status(timer)

    print("\n=== Let study run for 3 seconds ===")
    for _ in range(3):
        time.sleep(1)
        timer.tick()
        print_status(timer)
    # test pause
    print("\n=== Pause ===")
    timer.pause()
    print_status(timer)

    before = timer.time_left()

    time.sleep(3)
    timer.tick()

    print("\n=== Verify timer stayed paused ===")
    print(f"Before pause: {before:.1f}")
    print(f"After  pause: {timer.time_left():.1f}")
    # test resume
    print("\n=== Resume ===")
    timer.resume()

    for _ in range(3):
        time.sleep(1)
        timer.tick()
        print_status(timer)
    # test finish study session
    print("\n=== Force study completion ===")
    timer.remaining = 1

    time.sleep(2)
    event = timer.tick()

    print(f"Event returned: {event}")
    print_status(timer)

    print("\n=== Force break completion ===")
    timer.remaining = 1

    time.sleep(2)
    event = timer.tick()

    print(f"Event returned: {event}")
    print_status(timer)

    print("\n=== Test Complete ===")


if __name__ == "__main__":
    main()