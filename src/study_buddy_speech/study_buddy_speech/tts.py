########################################################################
# Filename: tts.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Description:
#   Text-to-speech output. output_audio(text) synthesizes speech with
#   espeak-ng (offline; Pi + Mac) or the macOS `say` fallback and plays it
#   through the speaker via sounddevice -- e.g. "I didn't get that" on a
#   failed recognition.
#
# How to use:
#   from study_buddy_speech.tts import output_audio
#   output_audio("I didn't get that")
#   python -m study_buddy_speech.tts        # quick manual test
########################################################################
"""Text-to-speech output for Pupper.

output_audio(text) synthesizes speech and plays it through the speaker with
sounddevice -- e.g. when ASR fails:  output_audio("I didn't get that").

Two backends, tried in order:
  1. espeak-ng -- offline, tiny, works on the Pi (`sudo apt install espeak-ng`)
                  and Mac (`brew install espeak-ng`). Preferred so Pi and laptop sound the same.
  2. macOS `say` -- always present on a Mac, so testing works with no install.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np
import sounddevice as sd


# Decode 16-bit PCM WAV bytes into (mono float32 samples, sample_rate).
def _wav_bytes_to_samples(data: bytes) -> tuple[np.ndarray, int]:
    """Decode 16-bit PCM WAV bytes into (mono float32 samples, sample_rate)."""
    with wave.open(io.BytesIO(data), "rb") as w:
        sample_rate = w.getframerate()
        channels = w.getnchannels()
        frames = w.readframes(w.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:  # collapse to mono
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, sample_rate


# Synthesize speech with espeak-ng (offline); returns None if espeak isn't installed.
def _synth_espeak(text: str, voice: str, wpm: int) -> tuple[np.ndarray, int] | None:
    if shutil.which("espeak-ng") is None:
        return None
    proc = subprocess.run(
        ["espeak-ng", "--stdout", "-v", voice, "-s", str(wpm), text],
        capture_output=True,
        check=True,
    )
    return _wav_bytes_to_samples(proc.stdout)


# Synthesize speech with the macOS `say` command; returns None if `say` is absent.
def _synth_macos_say(text: str, wpm: int) -> tuple[np.ndarray, int] | None:
    if shutil.which("say") is None:
        return None
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            ["say", "-o", path, "--data-format=LEI16@22050", "-r", str(wpm), text],
            check=True,
        )
        with open(path, "rb") as f:
            return _wav_bytes_to_samples(f.read())
    finally:
        if os.path.exists(path):
            os.remove(path)


# Speak `text` aloud through the default output device using sounddevice.
def output_audio(text: str, voice: str = "en", wpm: int = 160, blocking: bool = True) -> None:
    """Speak `text` through the default output device using sounddevice.

    Args:
        text: what Pupper should say. Empty string is a no-op.
        voice: espeak-ng voice name (ignored by the macOS fallback).
        wpm: speaking rate in words per minute.
        blocking: if True, wait until playback finishes before returning.
    """
    if not text:
        return

    result = _synth_espeak(text, voice, wpm) or _synth_macos_say(text, wpm)
    if result is None:
        raise RuntimeError(
            "No TTS backend found. Install espeak-ng "
            "(`sudo apt install espeak-ng` on the Pi, `brew install espeak-ng` on Mac)."
        )

    samples, sample_rate = result
    sd.play(samples, samplerate=sample_rate)
    if blocking:
        sd.wait()


if __name__ == "__main__":  # quick manual test:  python -m speech.tts
    output_audio("I didn't get that")
