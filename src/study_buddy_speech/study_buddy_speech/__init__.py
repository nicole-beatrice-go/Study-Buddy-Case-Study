########################################################################
# Filename: __init__.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Description:
#   Package init for the study_buddy_speech ROS 2 package. Pipeline:
#   microphone -> trigger -> Whisper ASR -> intent parser -> ROS topic.
#   Pieces are decoupled so the intent parser is unit-testable with no mic.
#
# How to use:
#   ros2 run study_buddy_speech speech     # see speech_node.py
########################################################################
"""Study Buddy Pupper speech package: voice commands + to-do dictation."""
