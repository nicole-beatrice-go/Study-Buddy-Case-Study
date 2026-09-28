########################################################################
# Filename: test_audio.py
# Student:  Nicole Go, nbgo@ucsd.edu
# Group:    Study Buddy
# Project:  Study Buddy Pupper -- Audio Playback Test (Final Project)
#
# Purpose:
#   To test audio and originally convert it to the binary format. Also makes audio louder
#
# Why this exists:
#   The Study Buddy behavior module uses sound effects for
#   moods. During development we needed
#   a way to:
#
#     1. Load audio files from disk
#     2. Test MP3-to-WAV conversion
#     3. Verify speaker output on the target hardware
#     4. Experiment with playback volume levels
#
# Workflow:
#   MP3 file -> librosa load 
#            -> soundfile write WAV
#            -> soundfile read WAV
#            -> amplify audio
#            -> sounddevice playback
#
# Usage:
#   python3 test_audio.py
#
# Dependencies:
#   pip install librosa sounddevice soundfile
########################################################################

import librosa
import sounddevice as sd
import soundfile as sf
import os

audio_path = "../audios/sad.mp3"

# convert to .wav
#audio, sr = librosa.load(audio_path, sr=None)

#print("shape:", audio.shape)
#print("sr:", sr)

# sf.write("output_sad.wav", audio, sr)

# play with soundfile and sounddevice
# multiply its amplitude to make it louder
audio, sr = sf.read("../audios/output_sad.wav")
audio_loud = audio * 5.0

sd.play(audio_loud, sr)
sd.wait()

print("done")