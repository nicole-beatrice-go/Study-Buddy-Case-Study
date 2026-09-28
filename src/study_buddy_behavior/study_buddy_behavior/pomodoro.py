########################################################################
# Filename: pomodoro.py
# Student:  Nicole Go, nbgo@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper
#
# Study Buddy Pupper -- Pomodoro session manager
#
# Why this exists:
#   The timer defines the overall structure of a study session: a study
#   period followed by a break period. It sends flags to FSM on if it is paused or not. 
#
#   The FSM node creates a Pomodoro Timer instance to call the resume and pause once it gets a trigger. There are also ticks to track time
#
#   FSM Node  -> owns PomodoroTimer
#   Timer     -> tracks study/break progress and vitality points
#   FSM Node  -> receives events and updates robot behavior/expression
#
# Responsibilities:
#   1. Manage study and break countdowns
#   2. Support pause/resume functionality
#   3.  Report phase-transition events:
#         'study_complete'
#         'break_over'
#   4.  Provide current session state and time remaining
#
# Used by:
#   study_buddy_fsm.py
#
# Dependencies:
#   study_buddy_behavior.config
#   study_buddy_behavior.points.PointSystem
########################################################################

import time

from study_buddy_behavior import config as cfg
from study_buddy_behavior.points import PointSystem


class PomodoroTimer:
    def __init__(self):
        self.points = PointSystem(start=cfg.START_VITALITY)
        self.phase = 'idle'          # idle | study | break
        self.paused = False
        self.remaining = 0.0         # seconds left in the current phase
        self.last_tick = time.time()
        self._away_penalty_applied = False   # dock the away penalty at most once per absence

    # start, pause, break, resume functions and flags
    def start_study(self):
        self.phase = 'study'
        self.paused = False
        self.remaining = cfg.STUDY_MIN * 60
        self.last_tick = time.time()

    def start_break(self):
        self.phase = 'break'
        self.paused = False
        self.remaining = cfg.BREAK_MIN * 60
        self.last_tick = time.time()

    def pause(self):
        if self.phase in ('study', 'break'):
            self.paused = True

    def resume(self):
        if self.paused:
            self.paused = False
            self.last_tick = time.time()

    # if continued with point system
    # def clear_away_penalty(self):
    #     """Re-arm the away penalty. Called when the user is back and studying, so
    #     the next time they're gone too long it can be charged again."""
    #     self._away_penalty_applied = False

    # def apply_away_penalty(self):
    #     """Dock AWAY_PENALTY vitality once per absence. Returns the new vitality,
    #     or None if it was already charged for this absence (never double-dock)."""
    #     if self._away_penalty_applied:
    #         return None
    #     self._away_penalty_applied = True
    #     return self.points.remove_points(cfg.AWAY_PENALTY)

    # tracks current state
    def current_mood(self):
        """The session's resting mood, used when the user is present (studying)."""
        return 'happy' if self.phase == 'break' else 'idle'

    # calls for how much time in session left
    def time_left(self):
        return max(0.0, self.remaining)

    # tracks ticks that pass in the state it is in and overall
    def tick(self):
        """Advance the clock. Returns an event string ('study_complete' /
        'break_over') or None. The FSM calls this once per tick."""
        if self.phase == 'idle' or self.paused:
            self.last_tick = time.time()
            return None

        now = time.time()
        self.remaining -= now - self.last_tick
        self.last_tick = now
        if self.remaining > 0:
            return None

        if self.phase == 'study':
            self.points.add_points(cfg.COMPLETE_REWARD)
            self.start_break()          # study finished -> roll into the break
            return 'study_complete'
        # break finished
        self.phase = 'idle'
        return 'break_over'
