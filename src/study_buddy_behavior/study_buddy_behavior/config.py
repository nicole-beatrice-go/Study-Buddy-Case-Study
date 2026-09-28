########
# config.py
#
# All tunable parameters for the Study Buddy behavior FSM live here.
########

# ---------------- Topics this FSM subscribes to ----------------
# These MUST match what study_zone_detector publishes. If you rename them in one
# place, rename them in the other.
TOPIC_PRESENT = 'study_zone/present'            # std_msgs/Bool    True = person present
TOPIC_SECONDS_AWAY = 'study_zone/seconds_away'  # std_msgs/Float32 seconds since seen

# ---------------- Presence detection (CPU toggle) ----------------
# The OAK presence/pose CV (study_zone_detector 'detector') is the HEAVIEST node
# on the Pi. Set False to run PHONE-ONLY: the FSM then treats the user as always
# present -- a tap starts the session immediately, and the away -> COUNTDOWN ->
# SLEEPING path is disabled (there is no person signal to drive it). Set True only
# if you actually run the presence node AND the Pi can handle pose + phone at once.
# When False, also stop LAUNCHING the presence node:
#   - launch:  ros2 launch study_buddy_behavior study_buddy.launch.py start_presence:=false
#   - tmux:    remove/comment the 'detector' window in run_buddy.sh
USE_PRESENCE = False

# Phone-distraction signal from study_zone_detector (phone_detector.py). The study
# clock PAUSES while the phone is OFF the desk during a study block (user likely on
# their phone) and resumes when it returns.
# MUST match TOPIC_PHONE_ON_DESK in study_zone_detector/config.py.
TOPIC_PHONE_ON_DESK = 'study_buddy/phone_on_desk'   # std_msgs/Bool  True = phone resting on desk

# Wake trigger. The robot can be woken either by becoming present again OR by a
# message on this topic (your voice/sound module, or a manual test, publishes
# std_msgs/Empty here).
TOPIC_WAKE = 'study_buddy/wake'                 # std_msgs/Empty   any message = "wake up"

# ---------------- Countdown ("study session end counting") ----------------
# When the user leaves, the robot starts a visible countdown. Return before it
# hits 0 and nothing bad happens; reach 0 and the robot goes to sleep.
COUNTDOWN_SECONDS = 120.0      # 2:00; set 60.0 for 1 min, 10.0 for fast testing

# ---------------- Sad recovery ----------------
# After being woken from sleep with the user back, the robot studies but SAD for
# this long, then recovers to happy.
SAD_RECOVER_SECONDS = 60.0

# ---------------- FSM loop ----------------
FSM_TICK = 0.2                 # how often the FSM re-evaluates (seconds)

# ---------------- Robot movement service ----------------
# When True, the expression node calls the lab2 GoPupper service ('pup_command')
# to actually move the robot. Leave False to develop with no robot -- moves are
# just logged. The service must be running:  ros2 run go_pupper_srv service
USE_PUPPER_SERVICE = True
# How long the expression node waits for pup_command at startup before giving up
# and falling back to logged moves (so a missing service never hangs the node).
PUPPER_SERVICE_TIMEOUT = 10.0

# ---------------- Face display ----------------
# When True, the expression node drives the MangDang mini-pupper screen. Leave
# False off-robot -- face changes are just logged (no MangDang package needed).
USE_DISPLAY = True
# Mini Pupper LCD width (px). Face images are resized to this once and cached
# before display, like lab2task5 tap_walk_social._preprocess_images -- otherwise a
# full-size image doesn't fit the screen.
DISPLAY_WIDTH = 320

# ---------------- Audio ----------------
# When True, the expression node plays mood sound clips through the speaker via a
# CLI player. Leave False off-robot -- sounds are just logged. Needs the player
# installed on the Pi:  sudo apt install mpg123
USE_AUDIO = True
# Command (+ flags) used to play an .mp3; the file path is appended. Swap to
# ['ffplay', '-nodisp', '-autoexit', '-loglevel', 'quiet'] if you use ffmpeg.
AUDIO_PLAYER_CMD = ['mpg123', '-q']
# The Mini Pupper speaker boots muted/low -- set volume to max once at startup,
# exactly like mini_pupper_bsp/demos/audio_test.py. WITHOUT this the clip decodes
# but you hear nothing. Card 0 / 'Headphone' per the BSP demo; adjust if your
# `amixer -c 0 scontrols` shows a different control name.
AUDIO_VOLUME_CMD = ['amixer', '-c', '0', 'sset', 'Headphone', '100%']

# ---------------- Speech (TTS) ----------------
# Spoken phrases. The FSM publishes short text on TOPIC_SAY and the expression
# node (sole audio owner) speaks it with espeak-ng -- offline, tiny, already used
# by study_buddy_speech/tts.py:  sudo apt install espeak-ng
# This is SEPARATE from the mood .mp3 clips above. Set False off-robot to log only.
USE_SPEECH = True
# Command (+ flags) used to speak; the text is appended as the final arg.
# -v = voice, -s = speaking rate (words/min). Shares the speaker with AUDIO above;
# AUDIO_VOLUME_CMD already unmutes it, so no extra setup is needed.
SPEECH_CMD = ['espeak-ng', '-v', 'en', '-s', '160']

# ================= Session timer (pomodoro.py) =================
# PomodoroTimer is a plain object OWNED by the FSM node (not its own node). The
# FSM calls its functions and is the single point of access to expression.

# ---------------- Session lengths ----------------
STUDY_MIN = 25                 # length of a study block (minutes)
BREAK_MIN = 5                  # length of a break (minutes)

# ---------------- Vitality points ----------------
START_VITALITY = 50            # proposal: a new buddy starts at 50/100
COMPLETE_REWARD = 10           # points gained when a study block completes
AWAY_PENALTY = 10              # points lost when the FSM reports the user gone too long

# ---------------- Inter-node topics ----------------
# Voice intents from study_buddy_speech (JSON: {name, slots, text}).
# This string MUST match TOPIC_VOICE_INTENT in study_buddy_speech/config.py.
TOPIC_VOICE_INTENT = 'study_buddy/voice_intent'    # std_msgs/String

# Mood requests. The FSM is the ONLY publisher (single point of access); the
# expression node is the only subscriber, so it is the sole owner of the hardware.
TOPIC_MOOD = 'study_buddy/mood'                    # std_msgs/String  idle|happy|sad|worried|sleepy

# Session timer text. The FSM is the ONLY publisher; the expression node (sole
# screen owner) renders it full-screen during a study block. A NON-empty string
# (e.g. "24 min") shows the timer; an EMPTY string releases the screen back to
# the current mood face. Keeping this on a topic -- not drawn by the FSM -- means
# only the expression node ever touches the LCD, so the timer and the mood face
# never fight over the screen.
TOPIC_TIMER = 'study_buddy/timer'                  # std_msgs/String  "N min" or "" to hide

# Spoken phrases. The FSM is the ONLY publisher; the expression node is the only
# subscriber and speaks the text (sole audio owner), so audio never collides.
TOPIC_SAY = 'study_buddy/say'                      # std_msgs/String  text for the robot to speak (TTS)

# ---------------- Touch sensor (study_buddy_touch node) ----------------
# A tap on a Mini Pupper pad STARTS a study session (from the START state, once
# the CV also sees you) and stirs the robot when it is sleeping. The touch node
# is a sensing node (like study_zone_detector): it only reads the pads and
# publishes here; the FSM decides what a tap means.
TOPIC_TOUCH = 'study_buddy/touch'                  # std_msgs/Empty  any message = "tapped"

# Mini Pupper touch-pad GPIO pins (BCM numbering), from lab2task5 /
# ~/mini_pupper_bsp/demos/touch_test.py. Pads are ACTIVE-LOW (read 0 = touched).
TOUCH_PIN_FRONT = 6
TOUCH_PIN_LEFT = 3
TOUCH_PIN_RIGHT = 16
TOUCH_POLL = 0.05                                  # how often the touch node polls (seconds)

# Which pads START/stir a session. The FRONT pad (6) is RESERVED for the speech
# node's push-to-talk (study_buddy_speech/config.py TOUCH_PIN=6), so it is left
# OUT here -- otherwise one front tap would both start a session AND trigger
# voice. Left pad (3) is the start button; right (16) also starts/stirs.
TOUCH_START_PINS = [TOUCH_PIN_LEFT, TOUCH_PIN_RIGHT]
