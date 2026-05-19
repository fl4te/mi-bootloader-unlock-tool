#!/usr/bin/env bash

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"
cd "$SCRIPT_DIR" || exit 1

tmux new-session -d -s mibox

tmux split-window -h

tmux split-window -v

tmux select-pane -t 0

tmux split-window -v

tmux select-layout tiled

tmux send-keys -t 0 "python3 script.py" C-m
sleep 1
tmux send-keys -t 0 "1" C-m

tmux send-keys -t 1 "python3 script.py" C-m
sleep 1
tmux send-keys -t 1 "2" C-m

tmux send-keys -t 2 "python3 script.py" C-m
sleep 1
tmux send-keys -t 2 "3" C-m

tmux send-keys -t 3 "python3 script.py" C-m
sleep 1
tmux send-keys -t 3 "4" C-m

tmux attach-session -t mibox
