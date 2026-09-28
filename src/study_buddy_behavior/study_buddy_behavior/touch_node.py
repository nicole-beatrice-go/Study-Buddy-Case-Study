########
# touch_node.py
#
# Study Buddy Pupper -- touch sensor node.
# Group: <your team name>
#
# Purpose:
#   A SENSING node (like study_zone_detector): read the Mini Pupper's capacitive
#   touch pads and publish a std_msgs/Empty on study_buddy/touch on each fresh
#   tap (rising edge). The FSM uses a tap to START a study session and to stir
#   the robot when it is sleeping. This node only senses -- the FSM decides.
#
# Wiring/pins from lab2task5 (which followed ~/mini_pupper_bsp/demos/touch_test.py):
#   front=GPIO6, left=GPIO3, right=GPIO16 (BCM). Pads are ACTIVE-LOW (0 = touched).
#
# Usage (after building + sourcing the workspace):
#   ros2 run study_buddy_behavior touch
#
# Off-robot / no GPIO: if RPi.GPIO is unavailable the node stays alive but
# publishes nothing. Fake a tap from another terminal with:
#   ros2 topic pub --once study_buddy/touch std_msgs/msg/Empty "{}"
#
# Author: <your name>
########

import rclpy
from rclpy.node import Node
from std_msgs.msg import Empty

from study_buddy_behavior import config as cfg


class TouchNode(Node):

    def __init__(self):
        super().__init__('study_buddy_touch')
        self.pub = self.create_publisher(Empty, cfg.TOPIC_TOUCH, 10)

        # Front pad (6) is reserved for the speech push-to-talk, so it is excluded
        # here (see TOUCH_START_PINS in config). Otherwise one front tap would both
        # start a session and trigger voice.
        self.pins = list(cfg.TOUCH_START_PINS)
        self.gpio = None
        try:
            import RPi.GPIO as GPIO
            self.gpio = GPIO
            GPIO.setmode(GPIO.BCM)
            for p in self.pins:
                GPIO.setup(p, GPIO.IN)
        except Exception as e:
            self.get_logger().warning(
                f'RPi.GPIO unavailable ({e}); touch node idle. Fake a tap with: '
                f'ros2 topic pub --once {cfg.TOPIC_TOUCH} std_msgs/msg/Empty "{{}}"')

        # Rising-edge detection: publish once per tap, not every poll while held.
        self.prev_touched = False
        self.timer = self.create_timer(cfg.TOUCH_POLL, self.poll)
        self.get_logger().info(
            f'study_buddy_touch started (pins={self.pins}, topic={cfg.TOPIC_TOUCH}).')

    def poll(self):
        if self.gpio is None:
            return
        # Active-low: GPIO reads 0 when a pad is touched.
        touched = any(not self.gpio.input(p) for p in self.pins)
        if touched and not self.prev_touched:
            self.pub.publish(Empty())
            self.get_logger().info('touch!')
        self.prev_touched = touched

    def destroy_node(self):
        if self.gpio is not None:
            self.gpio.cleanup()
        super().destroy_node()


def main():
    rclpy.init()
    node = TouchNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
