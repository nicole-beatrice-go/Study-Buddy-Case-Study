########
# Filename: behavior.py
# Student: Nicole Go, nbgo@ucsd.edu
# Group: Study Buddy
# Project: Study Buddy Pupper
#
# Purpose:
#   PupperBehavior is the  owner of all Study Buddy output:
#   - Face display
#   - Motion control
#   - Audio playback for sound effects
#
# Why this exists:
#   The FSM (study_buddy_fsm) and PomodoroTimer determine triggers for behavior
#
#   This file is responsible for managing all behaviors by handling functions for motion, display, and audio
#   It is to be called by FSM once the FSM gets the triggers
#   It also tracks which mood has which actions, movements, displays, and audios
#
# Key responsibilities:
#   1. Map mood to motion + face + audio
#   2. Have functions for each action
#
# Used by:
#   study_buddy_fsm.py
#
# Dependencies:
#   study_buddy_behavior.config
########

import os
import subprocess

import random

import librosa
import sounddevice as sd
import soundfile as sf

from study_buddy_behavior import config as cfg

# mood list
MOODS = ('idle', 'happy', 'sad', 'alert_phone_use', 'worried', 'sleepy')


class PupperBehavior:
    def __init__(self, node):
        self.node = node
        self.mood = 'idle'

        # manage display
        self.disp = None
        self.img_dir = None
        if cfg.USE_DISPLAY:
            from MangDang.mini_pupper.display import Display
            from ament_index_python.packages import get_package_share_directory
            from PIL import Image                     # lazy: only needed on-robot
            from resizeimage import resizeimage
            self._Image = Image
            self._resizeimage = resizeimage
            self.disp = Display()
            self.img_dir = os.path.join(
                get_package_share_directory('study_buddy_behavior'), 'images')

        # manage audio
        self.audio_dir = None
        if cfg.USE_AUDIO:
            from ament_index_python.packages import get_package_share_directory
            self.audio_dir = os.path.join(
                get_package_share_directory('study_buddy_behavior'), 'audios')
            try:
                subprocess.run(cfg.AUDIO_VOLUME_CMD, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                self.node.get_logger().warning('amixer not found; cannot set volume')

        # manage motion
        self.cli = None
        if cfg.USE_PUPPER_SERVICE:
            from pupper_interfaces.srv import GoPupper
            self._GoPupper = GoPupper
            self.cli = node.create_client(GoPupper, 'pup_command')
            waited = 0.0
            while not self.cli.wait_for_service(timeout_sec=1.0):
                waited += 1.0
                if waited >= cfg.PUPPER_SERVICE_TIMEOUT:
                    self.node.get_logger().warning(
                        f'pup_command service not found after {waited:.0f}s -- '
                        'continuing with moves LOGGED only. Start it with: '
                        'ros2 run go_pupper_srv service')
                    self.cli = None
                    break
                self.node.get_logger().info('waiting for pup_command service...')

        # mapping of moods
        self.mood_actions = {
            'happy':   {'motion': random.choice([self.dance, self.wag]),    'display': '../images/happy.jpg',   'audio': '../audios/output_happy.wav'},
            'sad':     {'motion': random.choice([self.crouch, self.backwards]), 'display': '../images/sad.jpg',     'audio': '../audios/output_sad.wav'},
            'alert_phone_use': {'motion': self.approach, 'display': '../images/sad.jpg',     'audio': '../audios/output_sad.wav'},
            'worried': {'display': '../images/sad.jpg'},      # COUNTDOWN: user just left
            'sleepy':  {'display': '../images/neutral.jpg'},  # SLEEPING: gone too long
            'idle':    {'display': '../images/neutral.jpg'},
        }
    # function to request pupper to move using one of the commands from interface
    def send_move_request(self, move_command):
        if self.cli is None:
            self.node.get_logger().info(f'[ROBOT] {move_command}')
            return
        req = self._GoPupper.Request()
        req.command = move_command
        future = self.cli.call_async(req)
        future.add_done_callback(
            lambda f: self._on_move_done(move_command, f))

    # track when done moving
    def _on_move_done(self, command, future):
        try:
            future.result()
        except Exception as e:                       # log any failure, never raise
            self.node.get_logger().warning(f'move {command!r} failed: {e}')

    # speak and play responses to voice commands
    def _play(self, audio_ref):
        filename = os.path.basename(audio_ref)
        if self.audio_dir is None:
            self.node.get_logger().info(f'[AUDIO] {filename}')
            return
        path = os.path.join(self.audio_dir, filename)
        try:
            subprocess.Popen(
                list(cfg.AUDIO_PLAYER_CMD) + [path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            self.node.get_logger().warning(
                f'audio player {cfg.AUDIO_PLAYER_CMD[0]!r} not found -- '
                '`sudo apt install mpg123` or set USE_AUDIO=False')

    def say(self, text):
        if not text:
            return
        if not cfg.USE_SPEECH:
            self.node.get_logger().info(f'[SPEAK] "{text}"')
            return
        try:
            subprocess.Popen(
                list(cfg.SPEECH_CMD) + [text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            self.node.get_logger().warning(
                f'TTS command {cfg.SPEECH_CMD[0]!r} not found -- '
                '`sudo apt install espeak-ng` or set USE_SPEECH=False')

    # use Display to show on screen
    def show(self, image_file):
        # image_file may be '../images/happy.jpg'; use just the filename.
        filename = os.path.basename(image_file)
        if self.disp is None:
            self.node.get_logger().info(f'[FACE] {filename}')
            return
        self.disp.show_image(self._resized_path(filename))

    # use draw to draw how many minutes are left on time
    def show_timer(self, text):
        if not text:
            self.update()                       # release the screen back to the face
            return
        if self.disp is None:
            self.node.get_logger().info(f'[TIMER] {text}')
            return
        # Lazy PIL import: only the on-robot path needs it (mirrors __init__).
        from PIL import Image, ImageDraw, ImageFont
        w = cfg.DISPLAY_WIDTH
        img = Image.new('RGB', (w, w), 'black')
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 72)
        except OSError:
            font = ImageFont.load_default()
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        draw.text(((w - (right - left)) / 2 - left,
                   (w - (bottom - top)) / 2 - top),
                  text, fill='white', font=font)
        path = os.path.join(self.img_dir, '_timer.png')
        img.save(path)
        self.disp.show_image(path)

    #resize images to fit on screen
    def _resized_path(self, filename):
        src = os.path.join(self.img_dir, filename)
        base, ext = os.path.splitext(filename)
        out_path = os.path.join(self.img_dir, f'{base}_RZ{ext or ".png"}')

        # Reuse the existing resized file unless it's missing or stale.
        if (os.path.exists(out_path)
                and os.path.getmtime(out_path) >= os.path.getmtime(src)):
            return out_path

        img = self._Image.open(src)
        # PNG with no alpha needs conversion (from pupper_display_test.py).
        if img.format == 'PNG' and img.mode != 'RGBA':
            old = img.convert('RGBA')
            img = self._Image.new('RGBA', old.size, (255, 255, 255))
        img = self._resizeimage.resize_width(img, cfg.DISPLAY_WIDTH)
        img.save(out_path, img.format or 'PNG')
        return out_path

    # movement commands from lab 2
    def dance(self):
        for i in range(2):
            self.send_move_request("move_left")
        for i in range(2):
            self.send_move_request("move_right")
        for i in range(3):
            self.send_move_request("move_backward")
        for i in range(3):
            self.send_move_request("move_forward")
    
    def backwards(self):
        for i in range(2):
            self.send_move_request('move_backward')

    def crouch(self):
        self.send_move_request('move_backward')   # 'crouch' is rejected by the service

    def approach(self):
        for i in range(2):
            self.send_move_request('move_forward')

    def wag(self):
        # 'wag' is rejected by the service -> wiggle with supported turns instead.
        self.send_move_request('turn_left')
        self.send_move_request('turn_right')

    # function to set and update moods
    def set_mood(self, mood):
        if mood not in self.mood_actions:
            self.node.get_logger().warning(f'Unknown mood: {mood}')
            return
        self.mood = mood
        self.update()

    # calls everything in the mapping depending on mood (motion, display, audio)
    def update(self):
        behavior = self.mood_actions.get(self.mood)
        if behavior is None:
            return
        if 'motion' in behavior:
            behavior['motion']()
        if 'display' in behavior:
            self.show(behavior['display'])
        if 'audio' in behavior:
            filename = os.path.basename(behavior['audio'])
            path = os.path.join(self.audio_dir, filename)

            audio, sr = sf.read(path)

            audio_loud = audio * 5.0
            audio_loud = np.clip(audio_loud, -1.0, 1.0)

            sd.play(audio_loud, sr)
            sd.wait()