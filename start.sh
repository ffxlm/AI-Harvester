#!/usr/bin/env bash
# ==============================================================================
# AI Harvester Suite - Local Runner Script
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
umask 000

# Check for .env
if [ ! -f ".env" ]; then
    echo "[!] Error: .env file not found in $SCRIPT_DIR"
    echo "    Please create .env with your credentials before running."
    exit 1
fi

# Check Python3
if ! command -v python3 &> /dev/null; then
    echo "[!] Error: python3 is not installed."
    exit 1
fi

# Check if dashboard is already running on port 5050
if lsof -Pi :5050 -sTCP:LISTEN -t >/dev/null 2>&1 || ss -tuln | grep -q ":5050 "; then
    echo "[*] Dashboard is already running on port 5050."
else
    echo "[*] Starting AI Harvester Suite Dashboard..."
    nohup python3 dashboard.py > /dev/null 2>&1 &
    sleep 1.5
fi

# Open in Default Browser (Google Chrome)
if command -v xdg-open &> /dev/null; then
    nohup xdg-open "http://localhost:5050" >/dev/null 2>&1 &
elif command -v google-chrome &> /dev/null; then
    nohup google-chrome "http://localhost:5050" >/dev/null 2>&1 &
fi

echo "[✓] Dashboard ready: http://localhost:5050"
