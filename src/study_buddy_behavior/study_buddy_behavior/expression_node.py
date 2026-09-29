########
# expression_node.py
#
# Study Buddy Pupper -- expression node.
# Group:
#
# Purpose:
#   The single owner of the robot's output hardware (face display, legs, audio).
#   It subscribes to ONE topic -- study_buddy/mood -- and renders whatever mood
#   the brains ask for via PupperBehavior. Because only this node drives the
#   hardware, study_buddy_fsm and pomodoro can never fight over the screen/motors.
#
# How it fits the system:
#   fsm / pomodoro  --study_buddy/mood (String)-->  expression node  -->  PupperBehavior
#
#   Subscribes:
#     study_buddy/mood  (std_msgs/String)  one of: idle | happy | sad | worried | sleepy
#
# Usage:
#   ros2 run study_buddy_behavior expression
#
# Author: <your name>
########

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from study_buddy_behavior import config as cfg
from study_buddy_behavior.behavior import PupperBehavior


class ExpressionNode(Node):

    def __init__(self):
        super().__init__('study_buddy_expression')
        self.pupper = PupperBehavior(self)
        self.create_subscription(String, cfg.TOPIC_MOOD, self.on_mood, 10)
        # Spoken nudges from the FSM. Routed through the same hardware owner as the
        # mood clips so audio output stays in one process.
        self.create_subscription(String, cfg.TOPIC_SAY, self.on_say, 10)
        # Session timer text from the FSM. Rendered full-screen during a study
        # block; an empty string releases the screen back to the current mood face.
        self.create_subscription(String, cfg.TOPIC_TIMER, self.on_timer, 10)
        self.get_logger().info(
            f'expression node started; listening on {cfg.TOPIC_MOOD}, '
            f'{cfg.TOPIC_SAY} and {cfg.TOPIC_TIMER}')

    def on_mood(self, msg):
        self.pupper.set_mood(msg.data)

    def on_say(self, msg):
        self.pupper.say(msg.data)

    def on_timer(self, msg):
        self.pupper.show_timer(msg.data)


def main():
    rclpy.init()
    node = ExpressionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
