import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'study_buddy_behavior'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        # Install the launch files so `ros2 launch study_buddy_behavior ...` works.
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        # Install the face images the expression node shows.
        (os.path.join('share', package_name, 'images'), glob('images/*.jpg')),
        # Install the mood sound clips the expression node plays.
        (os.path.join('share', package_name, 'audios'), glob('audios/*.mp3')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='your name',
    maintainer_email='ritalike4399@gmail.com',
    description='Study Buddy Pupper: behavior package -- excusing FSM, pomodoro session manager, and expression node.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'study_buddy = study_buddy_behavior.study_buddy_fsm:main',   # brain: FSM + owns the pomodoro timer
            'expression = study_buddy_behavior.expression_node:main',    # owns display/motors
            'touch = study_buddy_behavior.touch_node:main',              # touch pads -> study_buddy/touch
            'test_points = study_buddy_behavior.test_points:main',
            'test_pomodoro = study_buddy_behavior.test_pomodoro:main',
            'test_behavior = study_buddy_behavior.test_behavior:main',
        ],
    },
)
