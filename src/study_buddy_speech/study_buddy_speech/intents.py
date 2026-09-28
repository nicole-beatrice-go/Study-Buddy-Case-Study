########################################################################
# Filename: intents.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Description:
#   Maps recognized speech text to robot intents -- PAUSE, RESUME,
#   ADD_TODO, or UNKNOWN -- via a pure parse() function with NO hardware
#   dependency, so it is unit-tested directly (tests/test_intents.py).
#
# How to use:
#   from study_buddy_speech.intents import parse
#   parse("pause the session")      -> Intent(name="PAUSE", ...)
#   parse("add finish lab report")  -> Intent(name="ADD_TODO", slots={"task": ...})
########################################################################
"""Map recognized text to robot intents.

This is the heart of the speech module and the most important part to get right,
because it has NO hardware dependency: the "Test Speech Recognition" eval task
(page 7 of the proposal) runs as plain unit tests against parse() -- see
tests/test_intents.py.

Supported intents:
  PAUSE     -- pause the study session   ("pause", "pause the session", "stop", "hold on")
  RESUME    -- resume the session        ("resume", "continue", "keep going", "start")
  ADD_TODO  -- add an item to the to-do list, captured in slots["task"]
               ("add finish lab report", "to do read chapter 3", "remember to email TA")
  UNKNOWN   -- nothing matched; Pupper should ask the user to repeat
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# A parsed voice command: intent name + optional slots + the raw recognized text.
@dataclass
class Intent:
    name: str                              # PAUSE | RESUME | ADD_TODO | UNKNOWN
    slots: dict = field(default_factory=dict)
    text: str = ""                         # the raw recognized text, for logging/eval


# Prefixes that introduce a to-do item. Longest first so "add task" wins over "add".
# These are matched against normalized text (lowercase, punctuation stripped).
_ADD_PREFIXES = ("add task", "add", "todo", "to do", "remember to", "i need to", "i have to")

_PAUSE_WORDS = {"pause", "stop", "wait", "hold", "halt"}
_RESUME_WORDS = {"resume", "continue", "start", "go", "unpause", "begin"}

# Multi-word phrases checked before single words.
_PAUSE_PHRASES = ("hold on", "take a break", "pause the session", "pause session")
_RESUME_PHRASES = ("keep going", "carry on", "let's go", "resume the session")


# Lowercase and strip everything but letters/digits/spaces for matching.
def _normalize(text: str) -> str:
    """Lowercase and strip everything but letters, digits and spaces."""
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).strip()


# Turn recognized speech text into an Intent (pure function -> easy to test).
def parse(text: str) -> Intent:
    """Turn recognized speech into an Intent. Pure function -> easy to test."""
    norm = _normalize(text)
    if not norm:
        return Intent("UNKNOWN", text=text)

    # 1. To-do items first: an "add ..." utterance may itself contain stop-words.
    for prefix in _ADD_PREFIXES:
        if norm == prefix:
            # User asked to add something but gave no task; let caller prompt.
            return Intent("ADD_TODO", {"task": ""}, text)
        if norm.startswith(prefix + " "):
            task = norm[len(prefix) + 1:].strip()
            return Intent("ADD_TODO", {"task": task}, text)

    # 2. Multi-word command phrases.
    if any(p in norm for p in _PAUSE_PHRASES):
        return Intent("PAUSE", text=text)
    if any(p in norm for p in _RESUME_PHRASES):
        return Intent("RESUME", text=text)

    # 3. Single command words anywhere in the utterance.
    words = set(norm.split())
    if words & _PAUSE_WORDS:
        return Intent("PAUSE", text=text)
    if words & _RESUME_WORDS:
        return Intent("RESUME", text=text)

    return Intent("UNKNOWN", text=text)
