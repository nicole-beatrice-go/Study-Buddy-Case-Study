########################################################################
# Filename: mic_node.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Study Buddy Pupper -- microphone / trigger node (runs ON THE PI).
#
# Why this exists:
#   Whisper is too heavy for the Pi (it crashes the rest of the stack). So the
#   speech module is split in two: this light node owns the HARDWARE (touch-pad
#   trigger + USB mic + speaker), and a separate asr_node (on a laptop) does the
#   Whisper transcription. We only ever send audio out and a short string back --
#   no ML runs on the Pi.
#
#   Pi  : mic_node     trigger -> capture -> publish audio  (this file)
#   LAN : study_buddy/voice_audio (Int16MultiArray)
#   PC  : asr_node     Whisper -> intent -> publish study_buddy/voice_intent
#
#   Publishes:
#     study_buddy/voice_audio  (std_msgs/Int16MultiArray)  one buffer per utterance
#   Subscribes:
#     study_buddy/speak        (std_msgs/String)  phrase to speak on the Pi speaker
#
# Trigger (config.py TRIGGER): same as the old speech node --
#   'enter' -> press Enter, then speak
#   'gpio'  -> hold your own GPIO push-to-talk button (BUTTON_PIN -> GND)
#   'touch' -> hold a built-in Pupper touch pad (RPi.GPIO, active-low)
#
# Usage (after building + sourcing the workspace, on the Pi):
#   ros2 run study_buddy_speech mic
#
# Dependencies (pip / apt, NOT rosdep):
#   pip install sounddevice numpy        # mic capture (light)
#   sudo apt install espeak-ng           # spoken feedback (light)
#   RPi.GPIO                             # only for TRIGGER = 'touch' (already on the Pupper)
########################################################################

import threading

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int16MultiArray, String

from study_buddy_speech import config as cfg
from study_buddy_speech import recorder
from study_buddy_speech.tts import output_audio


# Pi-side node: capture audio and publish it; speak phrases sent by asr_node.
class MicNode(Node):

    # Set up the audio publisher, the speak subscription, and the trigger.
    def __init__(self):
        super().__init__('study_buddy_mic')

        # Audio out to the laptop's asr_node.
        self.audio_pub = self.create_publisher(Int16MultiArray, cfg.TOPIC_VOICE_AUDIO, 10)
        # Spoken feedback in: asr_node tells us what to say; we own the speaker.
        self.create_subscription(String, cfg.TOPIC_SPEAK, self.on_speak, 10)

        # Set up the trigger (identical options to the old speech node).
        self.button = None
        if cfg.TRIGGER == 'gpio':
            from gpiozero import Button  # Pi-only dependency, imported lazily
            self.button = Button(cfg.BUTTON_PIN)
            self.button.when_pressed = lambda: self.get_logger().info(
                f'button PRESSED (GPIO {cfg.BUTTON_PIN}) -- hold and speak')
            self.button.when_released = lambda: self.get_logger().info(
                f'button released (GPIO {cfg.BUTTON_PIN})')
            self.get_logger().info(f'push-to-talk on GPIO {cfg.BUTTON_PIN}')
        elif cfg.TRIGGER == 'touch':
            import RPi.GPIO as GPIO  # Pi-only dependency, imported lazily
            GPIO.setwarnings(False)
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(cfg.TOUCH_PIN, GPIO.IN)
            self.get_logger().info(
                f'push-to-talk on touch pad (BCM {cfg.TOUCH_PIN}, active-low)')
        else:  # 'enter'
            self.get_logger().info('press Enter, then speak')

        self.get_logger().info(
            f'mic_node up -- publishing audio on {cfg.TOPIC_VOICE_AUDIO!r}. '
            f'Run asr_node on the laptop (same ROS_DOMAIN_ID).')

    # Speak a phrase asr_node sent us, through the Pi speaker.
    def on_speak(self, msg):
        """Speak a phrase asr_node sent us, through the Pi speaker."""
        try:
            output_audio(msg.data)
        except Exception as exc:  # missing TTS backend must not kill the node
            self.get_logger().warn(f'tts unavailable: {exc}')

    # Capture one utterance using the configured trigger; return the audio buffer.
    def _capture_once(self):
        if cfg.TRIGGER == 'gpio':
            return recorder.record_while_pressed(self.button)
        if cfg.TRIGGER == 'touch':
            return recorder.record_while_touched(
                cfg.TOUCH_PIN,
                on_press=lambda: self.get_logger().info('touch PRESSED -- hold and speak'),
                on_release=lambda: self.get_logger().info('touch released'),
            )
        input('\n[ready] press Enter and speak> ')
        return recorder.record_until_silence()

    # Main loop: capture audio and publish it as int16 PCM for asr_node.
    def run(self):
        """Blocking capture loop. Spin happens on a background thread (see main)."""
        while rclpy.ok():
            audio = self._capture_once()
            if audio.size == 0:
                continue
            # float32 [-1, 1] -> int16 PCM, halving the bytes on the wire.
            pcm = np.clip(audio, -1.0, 1.0)
            pcm = (pcm * 32767.0).astype(np.int16)
            self.audio_pub.publish(Int16MultiArray(data=pcm.tolist()))
            self.get_logger().info(f'published {pcm.size} samples '
                                   f'({pcm.size / recorder.SAMPLE_RATE:.1f}s)')


# Entry point: spin in the background, run the capture loop, clean up GPIO.
def main():
    rclpy.init()
    node = MicNode()
    # Spin in the background so the speak subscription is serviced while the main
    # thread blocks in the capture loop.
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()
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
