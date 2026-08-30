#!/usr/bin/env bash
set -e

PROJECT="$HOME/Workspace/Final Project Network Cyber/Projects/AEGIS_IDEA3"
VENV="$PROJECT/venv"
SESSION="aegis-lab"

cd "$PROJECT"

echo "=== AEGIS IDEA 3 LAB DASHBOARD ==="

# --------------------------------------------------
# 1. Mosquitto
# --------------------------------------------------
echo "[1/4] Mosquitto"

if ! systemctl is-active --quiet mosquitto; then
    echo "Starting Mosquitto..."
    sudo systemctl start mosquitto
fi

if systemctl is-active --quiet mosquitto; then
    echo "[PASS] Mosquitto active"
else
    echo "[FAIL] Mosquitto failed"
    exit 1
fi

# --------------------------------------------------
# 2. Find ESP32 serial port
# --------------------------------------------------
echo "[2/4] ESP32 serial"

ESP_PORT=""

if [ -d /dev/serial/by-id ]; then
    ESP_PORT="$(find /dev/serial/by-id -type l 2>/dev/null | head -1)"
fi

if [ -z "$ESP_PORT" ]; then
    ESP_PORT="$(find /dev -maxdepth 1 \
        \( -name 'ttyUSB*' -o -name 'ttyACM*' \) \
        2>/dev/null | head -1)"
fi

if [ -z "$ESP_PORT" ]; then
    echo "[FAIL] ESP32 serial device not found"
    echo
    pio device list || true
    exit 1
fi

echo "[PASS] ESP32 = $ESP_PORT"

# --------------------------------------------------
# 3. Remove old tmux session
# --------------------------------------------------
echo "[3/4] tmux dashboard"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Old session '$SESSION' exists."
    echo "Stopping old session..."
    tmux kill-session -t "$SESSION"
fi

# --------------------------------------------------
# 4. Create dashboard
# --------------------------------------------------

# Pane 0 = SOC / Python server
tmux new-session -d \
    -s "$SESSION" \
    -n "AEGIS" \
    "cd \"$PROJECT\" && \
     source \"$VENV/bin/activate\" && \
     echo '=== SOC / server_admin.py ===' && \
     python3 server_admin.py; \
     exec bash"

# Pane 1 = Detector
tmux split-window -h \
    -t "$SESSION:AEGIS.0" \
    "cd \"$PROJECT\" && \
     echo '=== DETECTOR ===' && \
     sudo \"$VENV/bin/python\" detector.py; \
     exec bash"

# Pane 2 = ESP32 Serial
tmux split-window -v \
    -t "$SESSION:AEGIS.0" \
    "cd \"$PROJECT\" && \
     echo '=== ESP32 SERIAL : $ESP_PORT ===' && \
     pio device monitor -p \"$ESP_PORT\" -b 115200; \
     exec bash"

# Pane 3 = Mosquitto realtime log
tmux split-window -v \
    -t "$SESSION:AEGIS.1" \
    "echo '=== MOSQUITTO MQTT LOG ==='; \
     sudo journalctl -fu mosquitto; \
     exec bash"

# Arrange 2x2
tmux select-layout -t "$SESSION:AEGIS" tiled

# Pane titles
tmux select-pane -t "$SESSION:AEGIS.0" -T "SOC"
tmux select-pane -t "$SESSION:AEGIS.1" -T "DETECTOR"
tmux select-pane -t "$SESSION:AEGIS.2" -T "ESP32"
tmux select-pane -t "$SESSION:AEGIS.3" -T "MOSQUITTO"

echo "[4/4] READY"
echo
echo "========================================="
echo " AEGIS LAB DASHBOARD STARTED"
echo "========================================="
echo
echo "  SOC        = server_admin.py"
echo "  Detector   = detector.py"
echo "  ESP32      = $ESP_PORT"
echo "  Mosquitto  = realtime journal"
echo
echo "Attach:"
echo "  tmux attach -t $SESSION"
echo
echo "IMPORTANT:"
echo "  ARM ยังต้องกดเองบน SOC GUI"
echo

tmux attach -t "$SESSION"