########
# study_buddy.launch.py
#
# One-command startup for the whole Study Buddy pipeline:
#   OAK-D camera  ->  CV presence + phone-distraction detectors  ->  behavior FSM
#
# Run:
#   ros2 launch study_buddy_behavior study_buddy.launch.py
#
# Useful arguments:
#   start_camera:=false          # if you already launched the camera elsewhere
#   start_speech:=false          # skip voice (Whisper) to save CPU/RAM on the Pi
#   start_pupper_service:=false  # skip the GoPupper movement service
#
#   ros2 launch study_buddy_behavior study_buddy.launch.py start_camera:=false
#
# The GoPupper movement service (go_pupper_srv) provides 'pup_command' so the
# expression node can move the robot (when USE_PUPPER_SERVICE=True). It is started
# here before the expression node, and skipped if go_pupper_srv isn't installed.
#
# The camera include points at Lab 1's depthai_ros_driver camera.launch.py. If
# that package is not installed, the camera is skipped with a warning (the
# detector + FSM still start) -- just launch the camera yourself.
########

import os

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def launch_setup(context, *args, **kwargs):
    actions = []

    # --- OAK-D camera (optional) ---
    start_camera = LaunchConfiguration('start_camera').perform(context)
    if start_camera.lower() in ('true', '1', 'yes'):
        from ament_index_python.packages import get_package_share_directory
        try:
            cam_launch = os.path.join(
                get_package_share_directory('depthai_ros_driver'),
                'launch', 'camera.launch.py')
            actions.append(IncludeLaunchDescription(
                PythonLaunchDescriptionSource(cam_launch)))
        except Exception:
            actions.append(LogInfo(
                msg="[study_buddy] 'depthai_ros_driver' not found -- skipping "
                    "camera. Launch it yourself: "
                    "ros2 launch depthai_ros_driver camera.launch.py"))

    # --- CV presence detector (publishes study_zone/present) ---
    # Heaviest node on the Pi (MediaPipe pose). Off by default: phone-only mode
    # saves the CPU. Must agree with USE_PRESENCE in study_buddy_behavior/config.py
    # (the FSM treats the user as always present when presence is disabled).
    start_presence = LaunchConfiguration('start_presence').perform(context)
    if start_presence.lower() in ('true', '1', 'yes'):
        actions.append(Node(
            package='study_zone_detector',
            executable='detector',
            name='study_zone_detector',
            output='screen',
        ))
    else:
        actions.append(LogInfo(
            msg="[study_buddy] presence CV disabled (start_presence:=false) -- "
                "phone-only mode. Set USE_PRESENCE=False in behavior/config.py too."))

    # --- CV phone-distraction detector (publishes study_buddy/phone_on_desk) ---
    actions.append(Node(
        package='study_zone_detector',
        executable='phone',
        name='phone_detector',
        output='screen',
    ))

    # --- brain: FSM (excusing logic) + owns the pomodoro session timer ---
    actions.append(Node(
        package='study_buddy_behavior',
        executable='study_buddy',
        name='study_buddy_fsm',
        output='screen',
    ))

    # --- touch sensor (publishes study_buddy/touch; a tap starts a session) ---
    actions.append(Node(
        package='study_buddy_behavior',
        executable='touch',
        name='study_buddy_touch',
        output='screen',
    ))

    # --- GoPupper movement service (provides 'pup_command'; lab2 go_pupper_srv) ---
    # Started BEFORE the expression node so 'pup_command' is advertised before the
    # expression node's startup wait. The expression node calls it to move the
    # robot when USE_PUPPER_SERVICE is True. Skipped if go_pupper_srv isn't built
    # (expression then logs moves instead). NOTE: the service publishes cmd_vel --
    # the Mini Pupper motor bringup must also be running for the legs to move.
    start_pupper_service = LaunchConfiguration('start_pupper_service').perform(context)
    if start_pupper_service.lower() in ('true', '1', 'yes'):
        from ament_index_python.packages import (
            PackageNotFoundError, get_package_share_directory)
        try:
            get_package_share_directory('go_pupper_srv')
            actions.append(Node(
                package='go_pupper_srv',
                executable='service',
                name='go_pupper_service',
                output='screen',
            ))
        except PackageNotFoundError:
            actions.append(LogInfo(
                msg="[study_buddy] 'go_pupper_srv' not found -- skipping the "
                    "GoPupper service. Robot moves will be logged only. Start it "
                    "yourself: ros2 run go_pupper_srv service"))

    # --- expression node (sole owner of display/motors/audio) ---
    actions.append(Node(
        package='study_buddy_behavior',
        executable='expression',
        name='study_buddy_expression',
        output='screen',
    ))

    # --- speech recognition (optional: heavy deps; skipped if not built) ---
    start_speech = LaunchConfiguration('start_speech').perform(context)
    if start_speech.lower() in ('true', '1', 'yes'):
        from ament_index_python.packages import (
            PackageNotFoundError, get_package_share_directory)
        try:
            get_package_share_directory('study_buddy_speech')
            actions.append(Node(
                package='study_buddy_speech',
                executable='speech',
                name='study_buddy_speech',
                output='screen',
            ))
        except PackageNotFoundError:
            actions.append(LogInfo(
                msg="[study_buddy] 'study_buddy_speech' not built -- skipping "
                    "voice. Build it: colcon build --packages-select "
                    "study_buddy_speech"))

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            'start_camera',
            default_value='true',
            description='Also launch the OAK-D camera (depthai_ros_driver). '
                        'Set false if you start the camera yourself.'),
        DeclareLaunchArgument(
            'start_presence',
            default_value='false',
            description='Also launch the heavy presence/pose CV (study_zone_detector '
                        "'detector'). Default false = phone-only mode to save Pi CPU; "
                        'keep USE_PRESENCE in behavior/config.py in sync.'),
        DeclareLaunchArgument(
            'start_speech',
            default_value='true',
            description='Also launch study_buddy_speech (voice). Skipped '
                        'automatically if the package is not built.'),
        DeclareLaunchArgument(
            'start_pupper_service',
            default_value='true',
            description='Also launch the GoPupper movement service (go_pupper_srv) '
                        'that provides pup_command. Skipped automatically if the '
                        'package is not installed.'),
        OpaqueFunction(function=launch_setup),
    ])
