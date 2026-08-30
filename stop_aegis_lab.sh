#!/usr/bin/env bash

SESSION="aegis-lab"

echo "=== AEGIS IDEA 3 LAB STOP ==="

if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
    echo "[PASS] SOC / Detector / ESP32 monitor stopped"
else
    echo "[INFO] No tmux session found"
fi

echo
echo "Mosquitto was NOT stopped."
echo "To stop it manually:"
echo "  sudo systemctl stop mosquitto"