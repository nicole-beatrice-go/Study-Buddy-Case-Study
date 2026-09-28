########################################################################
# Filename: asr_node.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Study Buddy Pupper -- speech-to-intent node (runs ON A LAPTOP, not the Pi).
#
# Why this exists:
#   Whisper is too heavy for the Pi. This node does the heavy lifting off-board:
#   it subscribes to raw audio captured by mic_node (on the Pi), transcribes it
#   with Whisper, parses an intent, and publishes ONLY the small result string
#   back to the Pi's FSM. No audio hardware is touched here.
#
#   Pi  : mic_node     trigger -> capture -> study_buddy/voice_audio
#   PC  : asr_node     Whisper -> intent  -> study_buddy/voice_intent   (this file)
#
#   Subscribes:
#     study_buddy/voice_audio  (std_msgs/Int16MultiArray)  one buffer per utterance
#   Publishes:
#     study_buddy/voice_intent (std_msgs/String)   JSON {name, slots, text}
#     study_buddy/wake         (std_msgs/Empty)    mirrored on RESUME
#     study_buddy/speak        (std_msgs/String)   phrase for the Pi to speak (UNKNOWN)
#
# Usage (after building + sourcing the workspace, on the laptop):
#   ros2 run study_buddy_speech asr
#
# The laptop and Pi MUST share the same ROS_DOMAIN_ID and LAN so DDS discovers
# them. Verify with:  ros2 topic echo study_buddy/voice_audio   (tap + speak on Pi)
#
# Dependencies (pip): faster-whisper numpy        # the heavy part, laptop-only
########################################################################

import json

import numpy as np
import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty, Int16MultiArray, String

from study_buddy_speech import config as cfg
from study_buddy_speech import recorder
from study_buddy_speech.asr import Transcriber
from study_buddy_speech.intents import parse


# Laptop-side node: transcribe incoming audio and publish the parsed intent.
class AsrNode(Node):

    # Set up publishers, load Whisper, and subscribe to the audio topic.
    def __init__(self):
        super().__init__('study_buddy_asr')

        self.intent_pub = self.create_publisher(String, cfg.TOPIC_VOICE_INTENT, 10)
        self.wake_pub = self.create_publisher(Empty, cfg.TOPIC_WAKE, 10)
        self.speak_pub = self.create_publisher(String, cfg.TOPIC_SPEAK, 10)

        self.get_logger().info(f'loading Whisper model ({cfg.WHISPER_MODEL})...')
        self.transcriber = Transcriber(model_size=cfg.WHISPER_MODEL)

        self.create_subscription(
            Int16MultiArray, cfg.TOPIC_VOICE_AUDIO, self.on_audio, 10)
        self.get_logger().info(
            f'asr_node ready -- waiting for audio on {cfg.TOPIC_VOICE_AUDIO!r}')

    # Transcribe a received audio buffer and publish the parsed intent (+ wake/speak).
    def on_audio(self, msg):
        if not msg.data:
            return
        # int16 PCM from mic_node -> float32 [-1, 1] for Whisper.
        audio = np.asarray(msg.data, dtype=np.float32) / 32768.0

        text = self.transcriber.transcribe(audio, sample_rate=recorder.SAMPLE_RATE)
        intent = parse(text)
        self.get_logger().info(f'heard {text!r} -> {intent.name}')

        self.intent_pub.publish(String(
            data=json.dumps({
                'name': intent.name,
                'slots': intent.slots,
                'text': intent.text,
            })))

        if intent.name == 'RESUME' and cfg.PUBLISH_WAKE_ON_RESUME:
            self.wake_pub.publish(Empty())

        # Speaker lives on the Pi, so ask mic_node to say it instead of playing here.
        if intent.name == 'UNKNOWN' and cfg.SPEAK_ON_UNKNOWN:
            self.speak_pub.publish(String(data=cfg.UNKNOWN_PHRASE))


# Entry point: init ROS and spin the node.
def main():
    rclpy.init()
    node = AsrNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
