########################################################################
# Filename: config.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Description:
#   All tunable parameters for the Study Buddy speech node -- ROS topic
#   names, trigger choice and pins, Whisper model, and TTS feedback. Keep
#   every topic name and magic number here so you only tune in one place.
#
# How to use:
#   from study_buddy_speech import config as cfg
#   cfg.TRIGGER, cfg.TOUCH_PIN, cfg.WHISPER_MODEL, ...
########################################################################

# ---------------- ROS topics this node PUBLISHES ----------------
# The full parsed intent, as a JSON string:
#   {"name": "PAUSE"|"RESUME"|"ADD_TODO"|"UNKNOWN", "slots": {...}, "text": "..."}
# study_buddy_fsm (or a to-do/display node) subscribes to this. If you rename it
# here, rename it in the subscriber too.
TOPIC_VOICE_INTENT = 'study_buddy/voice_intent'   # std_msgs/String

# Wake trigger reused from study_buddy_behavior/config.py. The FSM already
# listens here (std_msgs/Empty = "wake up"). We mirror a RESUME voice command to
# it so saying "resume" wakes the robot with NO change to the FSM.
# This string MUST match TOPIC_WAKE in study_buddy_behavior/config.py.
TOPIC_WAKE = 'study_buddy/wake'                    # std_msgs/Empty
PUBLISH_WAKE_ON_RESUME = True

# ---------------- Trigger (how the node knows you're talking) ----------------
# How the node decides you're talking. Pick ONE:
#   'enter' : press Enter in the terminal, then speak (laptop / desk testing).
#   'gpio'  : hold your OWN push-to-talk button wired between BUTTON_PIN and GND.
#   'touch' : hold one of the Pupper's built-in touch pads (front/left/right).
#             Read with RPi.GPIO, exactly like the Lab 2 TapWalk controller.
#             RPi.GPIO reads the pin register directly, so it works even though the
#             kernel's gpio-keys driver also owns the line -- unlike gpiozero/lgpio,
#             whose Button() on the same pin fails with "GPIO busy".
TRIGGER = 'touch'

# --- used when TRIGGER == 'gpio' (your own button, on a FREE pin) ---
BUTTON_PIN = 17                # BCM pin number (gpiozero); 17 is unused on the Pupper

# --- used when TRIGGER == 'touch' (built-in pad via RPi.GPIO) ---
# BCM pin of the pad to use as push-to-talk. Pads are active-low (touched == 0).
# Mini Pupper pads (per the Lab 2 touch controller): front=6, left=3, right=16.
TOUCH_PIN = 6

# ---------------- Whisper (local ASR) ----------------
# 'tiny.en' is small/fast enough for the Raspberry Pi. Use 'base.en' on a laptop
# for more accurate to-do dictation.
WHISPER_MODEL = 'tiny.en'

# ---------------- Spoken feedback (TTS) ----------------
# When a command is not understood, Pupper says this out loud through the speaker.
SPEAK_ON_UNKNOWN = True
UNKNOWN_PHRASE = "I didn't get that"
