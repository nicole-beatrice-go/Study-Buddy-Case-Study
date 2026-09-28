########################################################################
# Filename: test_behavior.py
# Student:  Nicole Go, nbgo@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Behavior Test Utility (Final Project)
#
# Study Buddy Pupper -- behavior validation tool.
#
# Purpose:
#   Verify that the behavior executes motions and displays correctly.
#
# Why this exists:
#   The PupperBehavior class is responsible for coordinating robot
#   movement and expressions according to mood. Before
#   integrating these behaviors into the full Study Buddy FSM, we needed
#   a simple way to test each action individually.

# Tests performed:
#   Motions:
#     - dance()
#     - wag()
#     - crouch()
#     - backwards()
#     - approach()
#
#   Moods:
#     - happy
#     - sad
#     - alert_phone_use
#     - idle
#
# Usage:
#   ros2 run study_buddy_behavior test_behavior
#
# Expected outcome:
#   The robot performs each motion in sequence and displays each mood
#   before transitioning to the next one
#
# Dependencies:
#   rclpy
#   study_buddy_behavior.behavior.PupperBehavior
########################################################################

import time

import rclpy
from rclpy.node import Node

from study_buddy_behavior.behavior import PupperBehavior


class BehaviorTester(Node):
    def __init__(self):
        super().__init__('behavior_tester')

        self.behavior = PupperBehavior(self)
    # run motions
    def run_tests(self):
        self.get_logger().info("=== Testing motions ===")

        self.behavior.dance()
        time.sleep(2)

        self.behavior.wag()
        time.sleep(2)

        self.behavior.crouch()
        time.sleep(2)

        self.behavior.backwards()
        time.sleep(2)

        self.behavior.approach()
        time.sleep(2)

        self.get_logger().info("=== Testing moods ===")
    # run displays
        self.behavior.set_mood('happy')
        time.sleep(3)

        self.behavior.set_mood('sad')
        time.sleep(3)

        self.behavior.set_mood('alert_phone_use')
        time.sleep(3)

        self.behavior.set_mood('idle')
        time.sleep(3)

        self.get_logger().info("=== Tests complete ===")


def main():
    rclpy.init()

    tester = BehaviorTester()

    try:
        tester.run_tests()
    finally:
        tester.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()