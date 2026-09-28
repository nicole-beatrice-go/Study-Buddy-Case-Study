########################################################################
# Filename: asr.py
# Student:  Lele Zhao, l5zhao@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Speech Module (Final Project)
#
# Description:
#   Whisper-based speech-to-text. Wraps faster-whisper (tiny English, int8)
#   so callers just do Transcriber().transcribe(audio). Light enough for the
#   Raspberry Pi 4/5; cpu_threads is capped so it doesn't starve the stack.
#
# How to use:
#   from study_buddy_speech.asr import Transcriber
#   text = Transcriber().transcribe(audio)   # audio = mono float32 @ 16 kHz
########################################################################
"""Whisper-based speech-to-text.

Wraps faster-whisper so the rest of the code just calls Transcriber.transcribe(audio).
Defaults to the tiny English model with int8 weights, which is small and fast
enough to run on the Raspberry Pi 4/5 (the proposal's onboard compute).
"""
from __future__ import annotations

import numpy as np


# Loads Whisper once and turns audio buffers into text.
class Transcriber:
    # Load the faster-whisper model (tiny English, int8, capped CPU threads).
    def __init__(
        self,
        model_size: str = "tiny.en",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 2,
    ) -> None:
        # Imported here so the intent unit tests don't require faster-whisper.
        from faster_whisper import WhisperModel

        self.model = WhisperModel(model_size, device=device, compute_type=compute_type,cpu_threads=cpu_threads)

    # Transcribe a mono float32 buffer at 16 kHz into a text string.
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Transcribe a mono float32 buffer at 16 kHz into text."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        # beam_size=1 (greedy) keeps latency low; our vocabulary is small.
        segments, _ = self.model.transcribe(audio, language="en", beam_size=1)
        return " ".join(seg.text for seg in segments).strip()
