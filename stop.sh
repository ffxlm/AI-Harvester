#!/usr/bin/env bash
# ==============================================================================
# AI Harvester Suite - Stop Script
# ==============================================================================

echo "[*] Stopping AI Harvester Dashboard and active workers..."

# Kill dashboard process
pkill -f "python3 dashboard.py" 2>/dev/null

# Kill any lingering harvester scripts
pkill -f "register_dahl.py" 2>/dev/null
pkill -f "register_openrouter.py" 2>/dev/null
pkill -f "register_tokenharbor.py" 2>/dev/null
pkill -f "register_grok_tokens.py" 2>/dev/null

# Free port 5050 if still occupied
fuser -k 5050/tcp 2>/dev/null

sleep 1
echo "[✓] Dashboard and all Harvesters stopped successfully."
