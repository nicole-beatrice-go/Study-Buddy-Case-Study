########################################
# Filename: study_buddy_fsm.py
# Project:  Study Buddy Pupper -- Final Project (CSE 276B)
#
# Students (this file was written jointly by the whole team):
#   Juan Yin, j9yin@ucsd.edu          -- CV integration: presence + phone-gate
#                                        wiring into the FSM (subscriptions,
#                                        apply_focus_gate, _present).
#   Lele Zhao, l5zhao@ucsd.edu -- <their FSM contribution, e.g. core state
#                                        machine + Pomodoro session logic>.
#   <Nicole Go>, <nbgo@ucsd.edu> -- <behavior and pomodoro timer integration>.
#
# Description:
#   Study Buddy Pupper -- Behavior FSM node. This is the "brain" that reacts to
#   user presence and the phone-distraction signal (both from the CV nodes) and
#   runs a Pomodoro study session. It SUBSCRIBES to presence and phone state
#   (study_zone_detector), touch (touch_node), and voice intents
#   (study_buddy_speech); it OWNS the session timer (pomodoro.py); and it
#   publishes a single mood string that the expression node renders. Keeping the
#   FSM the single point of access to expression means nothing fights over the
#   screen, motors, or speaker.
#
#   The node runs two orthogonal layers:
#     * Presence FSM state : START / STUDYING / COUNTDOWN / SLEEPING / STUDYING_SAD
#     * Session phase      : idle / study / break   (inside PomodoroTimer)
#
#   State behavior:
#     START         fresh/happy, idle. Waiting to begin.
#                     -> tapped, THEN user present => STUDYING (start STUDY_MIN timer)
#     STUDYING      present, working. Session timer runs (study), then auto-rolls
#                   into a break; the break ignores presence.
#                     -> study block done => (break) ... break_over => START
#                     -> user leaves (during study) => COUNTDOWN (timer PAUSES)
#     COUNTDOWN     user just left. Visible grace timer (COUNTDOWN_SECONDS); the
#                   session timer is PAUSED (Option A: count only real focus).
#                     -> user returns => STUDYING (timer resumes)
#                     -> grace hits 0 => SLEEPING
#     SLEEPING      user never came back. Lies down, sad; docks points once.
#                     -> user present again        => STUDYING_SAD
#                     -> tapped / woken, still away => stirs, stays SLEEPING
#     STUDYING_SAD  came back after sleeping. Studies (timer resumes) but sad for
#                   a while.
#                     -> SAD_RECOVER_SECONDS pass => STUDYING
#                     -> user leaves again        => COUNTDOWN
#
#   Starting a session is TOUCH-ONLY (a tap, gated on the CV seeing you). Voice
#   still PAUSEs/RESUMEs an in-progress session but no longer starts a fresh one.
#
# How to use:
#   Usage:
#     # Build + source, then run this FSM:
#     cd ~/ros2_ws && colcon build --packages-select study_buddy_behavior
#     source install/setup.bash
#     ros2 run study_buddy_behavior study_buddy
#
#     # Run alongside the sensing + expression nodes:
#     ros2 run study_zone_detector detector       # presence (CV)
#     ros2 run study_zone_detector phone          # phone-distraction (CV)
#     ros2 run study_buddy_behavior touch         # touch (GPIO)
#     ros2 run study_buddy_behavior expression    # display / motors / audio
#     # Or start everything at once:
#     ros2 launch study_buddy_behavior study_buddy.launch.py
#
#     # Fake inputs for testing without hardware:
#     ros2 topic pub --once study_buddy/touch std_msgs/msg/Empty "{}"
#     ros2 topic pub --once study_zone/present std_msgs/msg/Bool "{data: true}"
#
# Acknowledgements: FSM structure modeled on Prof. Riek's
#   lab2task5/tap_walk_social.py.
########################################

import json
import time
from enum import Enum, auto

import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32, Empty, String

from study_buddy_behavior import config as cfg
from study_buddy_behavior.pomodoro import PomodoroTimer


# ---------------- FSM definition ----------------
class State(Enum):
    START = auto()          # fresh/happy, idle; waiting for a tap then presence
    STUDYING = auto()       # present, working (study or break phase)
    COUNTDOWN = auto()      # left; "session ending" grace running; timer PAUSED
    SLEEPING = auto()       # grace expired; asleep until woken
    STUDYING_SAD = auto()   # came back after sleeping; sad for a while


class StudyBuddyFSM(Node):

    def __init__(self):
        """
        Name:    __init__(self)
        Purpose: Construct the StudyBuddyFSM node. Initializes all input state,
                 subscribes to the sensing/touch/voice topics, creates and owns the
                 Pomodoro session timer, creates the mood/timer/say output
                 publishers (the FSM is the single point of access to expression),
                 boots into the START state, and starts the per-tick step() timer.
        @input   self: the node instance being constructed.
        @return  None. Leaves a fully wired ROS 2 node ready for rclpy.spin().
        """
        super().__init__('study_buddy_fsm')

        # ---- inputs from sensing nodes ----
        # Do NOT assume present at startup: START waits for the CV to see you.
        self.user_present = False
        self.seconds_away = 0.0
        self.wake_requested = False     # set by the wake topic, consumed each tick
        self.touch_requested = False    # set by the touch topic, consumed each tick
        self.armed = False              # tapped in START, waiting for presence
        self.show_neutral_until = 0.0   # brief neutral-face delay before the timer
        self.celebration_until = 0.0
        self.in_celebration = False
        # Phone-distraction input. Default True so a missing phone_detector never
        # blocks studying; the detector also reports True until the phone is
        # enrolled at rest, so we only ever pause on POSITIVE "picked up" evidence.
        self.phone_on_desk = True
        self.phone_paused = False       # True only while WE paused for the phone
        self.voice_paused = False       # True only while the user PAUSEd by voice

        self.create_subscription(
            Bool, cfg.TOPIC_PRESENT, self.on_present, 10)
        self.create_subscription(
            Float32, cfg.TOPIC_SECONDS_AWAY, self.on_seconds_away, 10)
        self.create_subscription(
            Bool, cfg.TOPIC_PHONE_ON_DESK, self.on_phone_on_desk, 10)
        self.create_subscription(
            Empty, cfg.TOPIC_WAKE, self.on_wake, 10)
        self.create_subscription(
            Empty, cfg.TOPIC_TOUCH, self.on_touch, 10)
        # ---- voice commands from study_buddy_speech ----
        self.create_subscription(
            String, cfg.TOPIC_VOICE_INTENT, self.on_voice, 10)

        # ---- the session timer is OWNED here (a plain object, not a node) ----
        # The FSM drives it directly: start_study / pause / resume / tick.
        self.session = PomodoroTimer()

        # ---- output: the FSM is the SINGLE point of access to expression ----
        # It publishes one mood; the expression node (sole hardware owner) renders
        # it. Presence/excusing moods take priority over the session mood. The FSM
        # NEVER touches the screen itself -- it only publishes here.
        self.mood_pub = self.create_publisher(String, cfg.TOPIC_MOOD, 10)
        self._mood = None               # last mood published, for de-duping

        # Session timer text. Same one-owner rule as mood: the FSM only publishes
        # the text ("N min" or "" to hide) and the expression node renders it.
        self.timer_pub = self.create_publisher(String, cfg.TOPIC_TIMER, 10)
        self._timer_text = None         # last timer text published, for de-duping

        # Spoken nudges. The FSM only publishes text; the expression node (sole
        # audio owner) does the actual TTS, so nothing here touches the speaker.
        self.say_pub = self.create_publisher(String, cfg.TOPIC_SAY, 10)

        # ---- FSM bookkeeping ----
        self.countdown_deadline = 0.0   # set on entering COUNTDOWN
        self.sad_until = 0.0            # set on entering STUDYING_SAD

        # Boot into START: fresh, waiting for a tap.
        self.state = State.START
        self.enter(State.START)

        # Drive the FSM off a timer; rclpy.spin() delivers the subscriptions.
        self.timer = self.create_timer(cfg.FSM_TICK, self.step)
        self.get_logger().info('study_buddy_fsm started.')

    # ---- subscription callbacks: ONLY store values, never act ----
    def on_present(self, msg):
        """
        Name:    on_present(self, msg)
        Purpose: Presence callback. Stores the latest present/away flag from my
                 presence_detector node; the step() loop acts on it.
        @input   msg: std_msgs/Bool from study_zone/present (True = person seen).
        @return  None. Sets self.user_present.
        """
        self.user_present = msg.data

    def on_seconds_away(self, msg):
        """
        Name:    on_seconds_away(self, msg)
        Purpose: Seconds-away callback. Stores how long the user has been unseen,
                 as reported by presence_detector.
        @input   msg: std_msgs/Float32 from study_zone/seconds_away.
        @return  None. Sets self.seconds_away.
        """
        self.seconds_away = msg.data

    def on_phone_on_desk(self, msg):
        """
        Name:    on_phone_on_desk(self, msg)
        Purpose: Phone-distraction callback. Stores whether the phone is resting
                 on the desk, as reported by my phone_detector node; the focus gate
                 in step() acts on it.
        @input   msg: std_msgs/Bool from study_buddy/phone_on_desk (True = on desk).
        @return  None. Sets self.phone_on_desk.
        """
        self.phone_on_desk = msg.data

    def on_wake(self, _msg):
        """
        Name:    on_wake(self, _msg)
        Purpose: Wake callback. Flags a wake request (e.g. from voice RESUME) that
                 step() consumes once to stir the robot out of SLEEPING.
        @input   _msg: std_msgs/Empty from study_buddy/wake (payload unused).
        @return  None. Sets self.wake_requested.
        """
        self.wake_requested = True

    def on_touch(self, _msg):
        """
        Name:    on_touch(self, _msg)
        Purpose: Touch callback. Flags a tap that step() consumes once -- a tap is
                 what starts a fresh study session (gated on the CV seeing you).
        @input   _msg: std_msgs/Empty from study_buddy/touch (payload unused).
        @return  None. Sets self.touch_requested.
        """
        self.touch_requested = True

    def on_voice(self, msg):
        """
        Name:    on_voice(self, msg)
        Purpose: Voice-intent callback from study_buddy_speech. Voice can
                 PAUSE/RESUME an in-progress session, but STARTING a fresh session
                 is touch-only. The pause is mirrored into the FSM (voice_paused)
                 so the result is OBSERVABLE: the robot speaks a confirmation, the
                 timer hides and the face shows, and the phone gate won't fight a
                 manual pause. ADD_TODO / UNKNOWN intents are ignored here.
        @input   msg: std_msgs/String, a JSON intent with a 'name' field
                 ('PAUSE' / 'RESUME' / 'ADD_TODO' / 'UNKNOWN').
        @return  None. May pause/resume the session, speak a confirmation, and
                 refresh the mood/timer as side effects.
        """
        try:
            intent = json.loads(msg.data)
        except json.JSONDecodeError:
            return
        name = intent.get('name')

        if name == 'PAUSE':
            if self.session.phase == 'idle':
                # Nothing is running to pause -- acknowledge instead of silently
                # doing nothing (a fresh session is started by a tap).
                self.speak("There's no session going yet. Tap me to start one.")
                return
            self.session.pause()
            self.voice_paused = True
            self.get_logger().info('session paused (voice)')
            self.speak("Okay, pausing. Say resume when you're ready.")

        elif name == 'RESUME':
            if self.voice_paused:
                self.voice_paused = False
                self.session.resume()
                self.get_logger().info('session resumed (voice)')
                self.speak("Resuming -- let's get back to it.")
            elif self.phone_paused:
                # Paused by the phone gate, not by voice: voice can't override the
                # real reason it stopped -- tell the user what to do.
                self.speak("Put your phone back on the desk and we'll keep going.")
                return
            else:
                self.speak("I'm already going. Keep it up!")
                return
        else:
            # ADD_TODO / UNKNOWN are handled by the to-do/display + speech sides.
            return

        # Reflect the change on the face/screen immediately (don't wait for the
        # next tick), then the regular step() loop keeps them in sync.
        self.refresh_mood()
        self.refresh_timer()

    # ---- presence signal (honors the phone-only CPU toggle) ----
    def _present(self):
        """
        Name:    _present(self)
        Purpose: Single source of truth for "should the FSM treat the user as
                 present?". In phone-only mode (cfg.USE_PRESENCE False) there is no
                 presence CV, so the user is treated as always present: a tap starts
                 the session right away and COUNTDOWN/SLEEPING never trigger. With
                 USE_PRESENCE True, it follows the CV's last report.
        @input   self: the node instance (reads self.user_present, cfg.USE_PRESENCE).
        @return  bool, whether the FSM should consider the user present.
        """
        return self.user_present if cfg.USE_PRESENCE else True

    # ---- output: single mood publisher (de-duped) ----
    def set_mood(self, mood):
        """
        Name:    set_mood(self, mood)
        Purpose: Publish a mood string for the expression node to render, de-duped
                 so it only publishes when the mood actually changes.
        @input   mood: str, the mood to show (e.g. 'idle', 'happy', 'sad',
                 'sleepy', 'alert_phone_use').
        @return  None. Publishes on study_buddy/mood when the mood changes.
        """
        if mood != self._mood:
            self._mood = mood
            self.mood_pub.publish(String(data=mood))

    def refresh_mood(self):
        """
        Name:    refresh_mood(self)
        Purpose: Decide the single mood to show for the current state and publish
                 it via set_mood. Presence/excusing moods (START, COUNTDOWN,
                 SLEEPING, STUDYING_SAD, voice/phone pauses) take priority over the
                 session's own mood.
        @input   self: the node instance (reads self.state, pause flags, session).
        @return  None. Calls set_mood as a side effect.
        """
        if self.state == State.START:
            self.set_mood('idle')           # fresh and ready, waiting for a tap
            self.show_neutral_until = time.time() + 1.0
        elif self.state == State.COUNTDOWN:
            self.set_mood('alert_phone_use')
        elif self.state == State.SLEEPING:
            self.set_mood('sleepy')
        elif self.state == State.STUDYING_SAD:
            self.set_mood('sad')
        elif self.voice_paused:
            # Paused by voice: the user has stepped out of studying -> sad face
            # (the timer is hidden too). On RESUME this clears and STUDYING's
            # session mood ('idle') shows the neutral face again.
            self.set_mood('sad')
        elif self.phone_paused:
            # STUDYING but the phone is off the desk -> nudge the user back.
            self.set_mood('alert_phone_use')
        else:  # STUDYING -> follow the session (idle while studying, happy on break)
            self.set_mood(self.session.current_mood())

    def speak(self, text):
        """
        Name:    speak(self, text)
        Purpose: Say a line aloud by publishing the text for the expression node
                 (the sole audio owner) to synthesize, so the FSM never touches the
                 speaker itself. Also logs the line so it shows in the FSM terminal.
        @input   text: str, the spoken nudge/confirmation to say.
        @return  None. Publishes on study_buddy/say and logs as side effects.
        """
        self.get_logger().info(f'[SPEAK] "{text}"')
        self.say_pub.publish(String(data=text))

    # ---- output: session timer text (de-duped), rendered by the expression node ----
    def set_timer(self, text):
        """
        Name:    set_timer(self, text)
        Purpose: Publish the session-timer text for the expression node to render,
                 de-duped so it only publishes on change (once per whole minute, or
                 once when showing/hiding). The FSM never draws the timer itself.
        @input   text: str, the timer label ('N min', or '' to hide the timer).
        @return  None. Publishes on study_buddy/timer when the text changes.
        """
        if text != self._timer_text:
            self._timer_text = text
            self.timer_pub.publish(String(data=text))

    def refresh_timer(self):
        """
        Name:    refresh_timer(self)
        Purpose: Decide whether the timer owns the screen and publish it via
                 set_timer. The timer shows full-screen ONLY during a study block
                 (after the brief neutral-face delay and when not phone/voice
                 paused); in every other state -- break, COUNTDOWN, SLEEPING,
                 START, celebration -- it publishes '' so the expression node falls
                 back to the mood face.
        @input   self: the node instance (reads self.state, self.session, pauses).
        @return  None. Calls set_timer as a side effect.
        """
        show = (self.state == State.STUDYING
                and self.session.phase == 'study'
                and not self.in_celebration
                and not self.phone_paused        # phone-nudge face wins over the timer
                and not self.voice_paused        # paused by voice -> show the face
                and time.time() >= self.show_neutral_until)
        if show:
            minutes = int(self.session.time_left()) // 60
            self.set_timer(f'{minutes} min')
        else:
            self.set_timer('')

    def apply_focus_gate(self):
        """
        Name:    apply_focus_gate(self)
        Purpose: Phone-distraction gate (the core of my CV-to-behavior
                 integration), run each tick while STUDYING in a study block. The
                 study clock should only run while the phone is on the desk: when it
                 is picked up (phone_on_desk False) the session pauses and the robot
                 nudges the user; when it returns the session resumes. Tracks
                 phone_paused so only a session WE paused is auto-resumed -- a manual
                 voice PAUSE is never overridden by the phone coming back. The break
                 phase ignores the phone, since the user is meant to rest.
        @input   self: the node instance (reads self.phone_on_desk, self.session,
                 self.voice_paused; writes self.phone_paused).
        @return  None. Pauses/resumes the session, speaks, and refreshes the mood
                 as side effects.
        """
        if self.session.phase == 'break':
            return
        if self.voice_paused:
            # A manual voice pause owns the session; don't let the phone gate
            # touch it (it would otherwise stay paused but flip our flags).
            return
        if not self.phone_on_desk:
            if not self.session.paused:
                self.session.pause()
                self.phone_paused = True
                self.get_logger().info('phone off desk -> session paused')
                self.speak("Phone's off the desk -- Are you sure? I will starve... I'll pause the timer until you put it back.")
                self.refresh_mood()
        elif self.phone_paused:
            self.session.resume()
            self.phone_paused = False
            self.get_logger().info('phone back on desk -> session resumed')
            self.speak("Phone's back -- I can eat some! Keep studying to feed me more.")
            self.refresh_mood()

    # ---- one-time actions when a state begins ----
    def enter(self, new_state):
        """
        Name:    enter(self, new_state)
        Purpose: Perform the one-time actions that fire when a state begins:
                 set self.state, run the per-state entry logic (arm in START,
                 resume the session in STUDYING/STUDYING_SAD, start the grace
                 deadline in COUNTDOWN, dock points in SLEEPING, etc.), speak the
                 matching line, and refresh the face. Per-tick logic lives in
                 step(), not here.
        @input   new_state: the State enum value to transition into.
        @return  None. Mutates self.state and related timers/flags and refreshes
                 the mood as side effects.
        """
        self.get_logger().info(f'==> {self.state.name} -> {new_state.name}')
        self.state = new_state

        if new_state == State.START:
            # Fresh/idle, waiting for a tap. Do NOT touch the session here -- a
            # fresh block is started in step() once tapped AND the CV sees you.
            self.armed = False
            self.speak("Tap me whenever you're ready to start a study session.")

        elif new_state == State.STUDYING:
            # user present: make sure the session is running again
            self.session.clear_away_penalty()
            self.phone_paused = False
            self.voice_paused = False       # entering STUDYING always resumes
            self.session.resume()

        elif new_state == State.COUNTDOWN:
            # Option A: pause the session the moment they leave; only real focus
            # time counts. We resume on return (STUDYING) or stay paused to sleep.
            self.countdown_deadline = time.time() + cfg.COUNTDOWN_SECONDS
            self.session.pause()
            self.speak("Are you coming back? I'll wait a couple of minutes.")

        elif new_state == State.SLEEPING:
            # gone too long: session already paused; dock points (once)
            self.speak("Okay... I'll take a nap. Wake me when you're back.")
            self.session.pause()
            lost = self.session.apply_away_penalty()
            if lost is not None:
                self.get_logger().info(
                    f'away too long: -{cfg.AWAY_PENALTY} points (vitality {lost})')

        elif new_state == State.STUDYING_SAD:
            # back after sleeping: resume the session
            self.sad_until = time.time() + cfg.SAD_RECOVER_SECONDS
            self.speak("Oh... you're back. I missed you.")
            self.session.clear_away_penalty()
            self.phone_paused = False
            self.voice_paused = False
            self.session.resume()

        self.refresh_mood()

    # ---- per-tick transition logic ----
    def step(self):
        """
        Name:    step(self)
        Purpose: The main FSM loop, called every cfg.FSM_TICK seconds. Advances the
                 Pomodoro session clock and handles its block/break events, then
                 evaluates the transitions for the current presence state (START ->
                 STUDYING on tap+presence, STUDYING -> COUNTDOWN on leave, COUNTDOWN
                 -> STUDYING/SLEEPING, SLEEPING -> STUDYING_SAD on return, etc.),
                 applies the phone focus gate while studying, keeps the face/timer
                 in sync, and consumes the one-shot wake/touch events.
        @input   self: the node instance (reads the stored sensor/voice state).
        @return  None. Drives state transitions and all expression output as side
                 effects.
        """
        now = time.time()
        woke = self.wake_requested      # snapshot, then consume at the end
        touched = self.touch_requested

        # advance the session clock and report block/break boundaries
        event = self.session.tick()
        if event == 'study_complete':
            self.get_logger().info(
                f'study block complete! +{cfg.COMPLETE_REWARD} points '
                f'(vitality {self.session.points.points})')
    
            self.in_celebration = True
            self.celebration_until = time.time() + 1.0
            self.session.pause()
        elif event == 'break_over':
            # Whole study+break cycle done: go back to START and wait for a tap.
            self.get_logger().info('break over')
            self.speak("Break's over! Tap me when you're ready for another session.")
            self.enter(State.START)

        if self.state == State.START:
            # Begin only after a tap AND the CV actually sees the user.
            if touched:
                self.armed = True
                self.speak("Got it -- sit down and I'll start the timer when I see you.")
                
            if self.armed and self._present():

                self.session.start_study()
                self.get_logger().info(f'study block started ({cfg.STUDY_MIN} min)')
                # Brief neutral-face delay before the timer takes the screen.
                self.show_neutral_until = time.time() + 1.0
                self.enter(State.STUDYING)

        elif self.state == State.STUDYING:
            if self.in_celebration:
                # Study block just finished: hold the happy face (refresh_mood
                # shows it; refresh_timer keeps the timer hidden), then roll into
                # the break once the short celebration is over.
                if now >= self.celebration_until:
                    self.in_celebration = False
                    self.session.start_break()
            elif self.session.phase != 'break' and not self._present():
                # Left during a study block -> grace countdown (timer pauses).
                self.enter(State.COUNTDOWN)
            elif self.session.phase == 'study':
                # Present and studying: the phone-distraction gate runs each tick.
                self.apply_focus_gate()
            # break phase: the user is resting -- ignore presence, just let the
            # clock run until 'break_over' sends us back to START.

        elif self.state == State.COUNTDOWN:
            if self._present():
                # Came back in time -- resume; session timer untouched (paused).
                self.enter(State.STUDYING)
            elif now >= self.countdown_deadline:
                self.enter(State.SLEEPING)

        elif self.state == State.SLEEPING:
            # Becoming present resumes studying. A tap/wake with no one there
            # just stirs and goes back to sleep.
            if self._present():
                self.enter(State.STUDYING_SAD)
            elif woke or touched:
                self.speak("Mmm? ...no one there. Back to sleep.")

        elif self.state == State.STUDYING_SAD:
            if self.session.phase != 'break' and not self._present():
                self.enter(State.COUNTDOWN)      # left again
            elif now >= self.sad_until:
                self.enter(State.STUDYING)        # mood recovered
            else:
                # Still sad but present: phone gate applies here too.
                self.apply_focus_gate()

        self.refresh_mood()             # keep the face in sync (session may have changed it)
        self.refresh_timer()            # show/hide the timer for the current state
        self.wake_requested = False     # consume events each tick
        self.touch_requested = False


def main():
    """
    Name:    main()
    Purpose: ROS 2 entry point for the `study_buddy` console script. Initializes
             rclpy, constructs the StudyBuddyFSM node, spins it until interrupted,
             then destroys the node and shuts rclpy down.
    @input   None.
    @return  None.
    """
    rclpy.init()
    node = StudyBuddyFSM()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
