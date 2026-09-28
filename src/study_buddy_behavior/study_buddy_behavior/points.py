########
# points.py
#
# Study Buddy Pupper -- vitality score (NOT a node).
#
# Pure bookkeeping: the buddy starts at START_VITALITY (proposal: 50/100) and
# gains/loses points over a session. This class deliberately does NOT touch the
# display or motors -- the Pomodoro node decides what mood to show when points
# change and publishes it on study_buddy/mood. Keeping points hardware-free means
# only the expression node ever drives the robot.
########


class PointSystem:
    def __init__(self, start):
        self.points = start

    def add_points(self, num):
        self.points += num
        return self.points

    def remove_points(self, num):
        self.points -= num
        return self.points
