########################################################################
# Filename: recorder.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Description:
#   Microphone capture with a pluggable trigger. Returns a mono float32
#   buffer at 16 kHz for the transcriber. Three triggers: silence-based
#   (laptop), gpiozero button, and a built-in touch pad via RPi.GPIO.
#
# How to use:
#   from study_buddy_speech import recorder
#   audio = recorder.record_until_silence()           # laptop
#   audio = recorder.record_while_pressed(button)     # Pi GPIO button
#   audio = recorder.record_while_touched(pin)        # Pi touch pad
########################################################################
"""Microphone capture with a pluggable trigger.

Both functions return a mono float32 numpy buffer at SAMPLE_RATE that
asr.Transcriber.transcribe() consumes directly.

  record_until_silence()  -- laptop dev: you press Enter (in commands.py), speak,
                             and it auto-stops after a beat of silence.
  record_while_pressed()  -- on the Pi: hold a gpiozero GPIO push-to-talk button,
                             speak, release to stop. For your OWN button on a free pin.
  record_while_touched()  -- on the Pi: hold a built-in touch pad (front/rear/...).
                             Read with RPi.GPIO (active-low). RPi.GPIO accesses the
                             pin register directly, so it works even though the
                             kernel gpio-keys driver also owns the line -- unlike
                             gpiozero/lgpio, which errors "GPIO busy".
"""
from __future__ import annotations

import time

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
_BLOCK_SECONDS = 0.1
_BLOCK = int(SAMPLE_RATE * _BLOCK_SECONDS)


# Return an empty (zero-length) float32 audio buffer.
def _empty() -> np.ndarray:
    return np.zeros(0, dtype=np.float32)


# Record until a beat of silence (or max_seconds) -- laptop dev, no button needed.
def record_until_silence(
    max_seconds: float = 8.0,
    silence_rms: float = 0.01,
    trailing_silence: float = 1.0,
) -> np.ndarray:
    """Record until ~trailing_silence seconds of quiet (or max_seconds), whichever
    comes first. Used for laptop development where there is no GPIO button."""
    needed_silent = int(trailing_silence / _BLOCK_SECONDS)
    max_blocks = int(max_seconds / _BLOCK_SECONDS)
    chunks: list[np.ndarray] = []
    silent_blocks = 0
    started = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", blocksize=_BLOCK
    ) as stream:
        for _ in range(max_blocks):
            data, _overflow = stream.read(_BLOCK)
            mono = data[:, 0].copy()
            chunks.append(mono)
            rms = float(np.sqrt(np.mean(mono ** 2)))
            if rms >= silence_rms:
                started = True
                silent_blocks = 0
            elif started:
                silent_blocks += 1
                if silent_blocks >= needed_silent:
                    break

    return np.concatenate(chunks) if chunks else _empty()


# Record while a gpiozero button is held down (Pi push-to-talk, your own button).
def record_while_pressed(button, max_seconds: float = 15.0) -> np.ndarray:
    """Record for as long as a gpiozero Button is held down (Raspberry Pi).

    `button` is a gpiozero.Button. Blocks until the button is pressed, captures
    while held, and stops on release. max_seconds is a safety cap.
    """
    max_blocks = int(max_seconds / _BLOCK_SECONDS)
    chunks: list[np.ndarray] = []

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", blocksize=_BLOCK
    ) as stream:
        button.wait_for_press()
        for _ in range(max_blocks):
            if not button.is_pressed:
                break
            data, _overflow = stream.read(_BLOCK)
            chunks.append(data[:, 0].copy())

    return np.concatenate(chunks) if chunks else _empty()


# Record while a built-in touch pad is held (Pi, RPi.GPIO, active-low).
def record_while_touched(
    pin: int,
    on_press=None,
    on_release=None,
    max_seconds: float = 15.0,
    poll_seconds: float = 0.01,
) -> np.ndarray:
    """Hold-to-talk via a built-in touch pad read with RPi.GPIO (active-low).

    The pad must already be set up (GPIO.setmode/GPIO.setup) by the caller. Blocks
    until the pad is touched, records while it is held, stops on release. RPi.GPIO
    reads the pin register directly, so this works even though the kernel gpio-keys
    driver owns the line. on_press/on_release are optional no-arg logging callbacks;
    max_seconds is a safety cap so a stuck pad can't record forever.
    """
    import RPi.GPIO as GPIO  # Pi-only dependency, imported lazily

    # True while the pad is being touched (pads read 0 when touched).
    def touched() -> bool:
        return not GPIO.input(pin)   # pads are active-low: 0 == touched

    # Block until the pad is first touched.
    while not touched():
        time.sleep(poll_seconds)
    if on_press is not None:
        on_press()

    max_blocks = int(max_seconds / _BLOCK_SECONDS)
    chunks: list[np.ndarray] = []
    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="float32", blocksize=_BLOCK
    ) as stream:
        for _ in range(max_blocks):
            if not touched():
                break
            data, _overflow = stream.read(_BLOCK)
            chunks.append(data[:, 0].copy())
    if on_release is not None:
        on_release()

    return np.concatenate(chunks) if chunks else _empty()
