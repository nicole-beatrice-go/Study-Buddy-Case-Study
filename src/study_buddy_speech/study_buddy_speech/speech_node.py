########################################################################
# Filename: speech_node.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Study Buddy Pupper -- Speech Recognition node.
#
# Purpose:
#   Listen for the user's voice, turn it into an intent, and publish that intent
#   so the behavior controller (study_buddy_fsm) and the to-do display can react.
#
# How it fits the system:
#   USB mic -> trigger -> Whisper (ASR) -> intents.parse() -> ROS topics
#
#   Publishes:
#     study_buddy/voice_intent  (std_msgs/String)  JSON: {name, slots, text}
#                                 name = PAUSE | RESUME | ADD_TODO | UNKNOWN
#     study_buddy/wake          (std_msgs/Empty)   sent on a RESUME command, so
#                                 saying "resume" wakes the FSM with no FSM change.
#
#   Speaks back (tts.py): on an unrecognized command, Pupper says
#   "I didn't get that" through the speaker.
#
# Trigger (config.py TRIGGER):
#   'enter' -> press Enter, then speak               (laptop / desk testing)
#   'gpio'  -> hold your own GPIO push-to-talk button (BUTTON_PIN -> GND)
#   'touch' -> hold a built-in Pupper touch pad       (kernel gpio-keys via evdev)
#
# Usage (after building + sourcing the workspace):
#   ros2 run study_buddy_speech speech
#
# Dependencies (pip / apt, NOT rosdep -- see package.xml):
#   pip install faster-whisper sounddevice numpy
#   sudo apt install espeak-ng
#   pip install gpiozero lgpio        # only for TRIGGER = 'gpio'
#   RPi.GPIO                          # only for TRIGGER = 'touch' (already on the Pupper)
########################################################################

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, String

from study_buddy_speech import config as cfg
from study_buddy_speech import recorder
from study_buddy_speech.asr import Transcriber
from study_buddy_speech.intents import parse
from study_buddy_speech.tts import output_audio


# ROS node: capture -> transcribe -> parse -> publish voice intents (all-in-one).
class SpeechNode(Node):

    # Set up publishers, load the Whisper model, and configure the chosen trigger.
    def __init__(self):
        super().__init__('study_buddy_speech')

        # Publishers consumed by the behavior controller / display.
        self.intent_pub = self.create_publisher(String, cfg.TOPIC_VOICE_INTENT, 10)
        self.wake_pub = self.create_publisher(Empty, cfg.TOPIC_WAKE, 10)

        self.get_logger().info(f'loading Whisper model ({cfg.WHISPER_MODEL})...')
        self.transcriber = Transcriber(model_size=cfg.WHISPER_MODEL)

        # Set up the trigger.
        self.button = None
        if cfg.TRIGGER == 'gpio':
            from gpiozero import Button  # Pi-only dependency, imported lazily
            self.button = Button(cfg.BUTTON_PIN)
            # Log every physical edge so it's obvious the button is wired and the
            # hold-to-talk window matches how long you actually held it.
            self.button.when_pressed = lambda: self.get_logger().info(
                f'button PRESSED (GPIO {cfg.BUTTON_PIN}) -- hold and speak')
            self.button.when_released = lambda: self.get_logger().info(
                f'button released (GPIO {cfg.BUTTON_PIN})')
            self.get_logger().info(f'push-to-talk on GPIO {cfg.BUTTON_PIN}')
        elif cfg.TRIGGER == 'touch':
            # Built-in touch pad read with RPi.GPIO (like the Lab 2 TapWalk node).
            # Direct register access works even though gpio-keys owns the line.
            import RPi.GPIO as GPIO  # Pi-only dependency, imported lazily
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(cfg.TOUCH_PIN, GPIO.IN)
            self.get_logger().info(
                f'push-to-talk on touch pad (BCM {cfg.TOUCH_PIN}, active-low)')
        else:  # 'enter'
            self.get_logger().info('press Enter, then speak')

    # Capture one utterance using the configured trigger; return the audio buffer.
    def _capture_once(self):
        if cfg.TRIGGER == 'gpio':
            return recorder.record_while_pressed(self.button)
        if cfg.TRIGGER == 'touch':
            return recorder.record_while_touched(
                cfg.TOUCH_PIN,
                on_press=lambda: self.get_logger().info(
                    'touch PRESSED -- hold and speak'),
                on_release=lambda: self.get_logger().info('touch released'),
            )
        input('\n[ready] press Enter and speak> ')
        return recorder.record_until_silence()

    # Main loop: capture, transcribe, parse, publish the intent, speak on UNKNOWN.
    def run(self):
        """Blocking capture loop. This node only publishes, so it needs no spin."""
        while rclpy.ok():
            audio = self._capture_once()
            if audio.size == 0:
                continue

            text = self.transcriber.transcribe(audio)
            intent = parse(text)
            self.get_logger().info(f'heard {text!r} -> {intent.name}')

            # Publish the full intent for any subscriber.
            self.intent_pub.publish(String(
                data=json.dumps({
                    'name': intent.name,
                    'slots': intent.slots,
                    'text': intent.text,
                })))

            # Mirror RESUME to the FSM's existing wake topic.
            if intent.name == 'RESUME' and cfg.PUBLISH_WAKE_ON_RESUME:
                self.wake_pub.publish(Empty())

            # Speak back when we didn't understand.
            if intent.name == 'UNKNOWN' and cfg.SPEAK_ON_UNKNOWN:
                try:
                    output_audio(cfg.UNKNOWN_PHRASE)
                except Exception as exc:  # missing TTS backend must not kill the node
                    self.get_logger().warn(f'tts unavailable: {exc}')


# Entry point: init ROS, run the node, and clean up GPIO on exit.
def main():
    rclpy.init()
    node = SpeechNode()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if cfg.TRIGGER == 'touch':
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
