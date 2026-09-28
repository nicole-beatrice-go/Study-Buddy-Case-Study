#!/usr/bin/env bash
# run_buddy.sh -- start each Study Buddy node in its own tmux window.
#
# Usage:
#   chmod +x ~/run_buddy.sh
#   ~/run_buddy.sh
#
# tmux controls: Ctrl-b then 0-7 to switch windows | Ctrl-b n/p next/prev
#                Ctrl-b d to detach (nodes keep running; reattach: tmux attach -t buddy)
# Stop everything: tmux kill-session -t buddy
#
# Running in tmux means a WiFi/SSH drop won't kill the nodes.

S=buddy
SETUP='source ~/ros2_ws/install/setup.bash'
CAM_PARAMS=/home/ubuntu/oak_rgb.yaml   # RGB-only params (no on-device NN)

# If a 'buddy' session already exists, attach to it instead of stacking another.
if tmux has-session -t "$S" 2>/dev/null; then
    echo "tmux session '$S' already running -- attaching. (kill it with: tmux kill-session -t $S)"
    exec tmux attach -t "$S"
fi

# Window 0: camera. Wait for it before the CV nodes subscribe.
tmux new-session -d -s "$S" -n camera \
    "$SETUP; ros2 launch depthai_ros_driver camera.launch.py params_file:=$CAM_PARAMS; bash"
sleep 8

tmux new-window -t "$S" -n phone      "$SETUP; ros2 run study_zone_detector phone; bash"
# Presence/pose CV (heaviest node) is DISABLED -- phone-only mode to save Pi CPU.
# Keep USE_PRESENCE=False in study_buddy_behavior/config.py so the FSM treats the
# user as always present. To re-enable presence, uncomment the line below AND set
# USE_PRESENCE=True.
# tmux new-window -t "$S" -n detector   "$SETUP; ros2 run study_zone_detector detector; bash"
tmux new-window -t "$S" -n fsm        "$SETUP; ros2 run study_buddy_behavior study_buddy; bash"
tmux new-window -t "$S" -n touch      "$SETUP; ros2 run study_buddy_behavior touch; bash"
tmux new-window -t "$S" -n expression "$SETUP; ros2 run study_buddy_behavior expression; bash"
tmux new-window -t "$S" -n pupper     "$SETUP; ros2 run go_pupper_srv service; bash"
tmux new-window -t "$S" -n speech     "$SETUP; ros2 run study_buddy_speech speech; bash"

tmux attach -t "$S"
