#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dahl Inference Key Tester
Tests all keys in keys/dahl_keys.txt against Dahl's OpenAI-compatible completions endpoint.
"""

import sys, os, urllib.request, urllib.error, json, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "keys", "dahl_keys.txt")

if not os.path.exists(KEYS_FILE):
    print(f"[!] Keys file not found at: {KEYS_FILE}")
    sys.exit(1)

with open(KEYS_FILE, "r", encoding="utf-8") as f:
    lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

print(f"\n{'='*60}")
print(f"[*] Testing {len(lines)} Dahl API Key(s) in {KEYS_FILE}")
print(f"{'='*60}\n")

valid_count = 0
for i, line in enumerate(lines, 1):
    parts = line.split("|")
    if len(parts) >= 2:
        username, key = parts[0], parts[1]
    else:
        username, key = "unknown", line

    print(f"[{i}/{len(lines)}] Testing: {username}")
    print(f"       Key: {key[:10]}...{key[-6:]}")

    start_t = time.time()
    url = "https://inference.dahl.global/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    data = {
        "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(data).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            dur = time.time() - start_t
            res = json.loads(resp.read().decode("utf-8"))
            valid_count += 1
            print(f"       Status: ✅ ACTIVE (Latency: {dur:.2f}s, Model: DeepSeek-V4-Flash)\n")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"       Status: ❌ FAILED (HTTP {e.code}: {err[:80]})\n")
    except Exception as e:
        print(f"       Status: ❌ ERROR ({e})\n")

print(f"{'='*60}")
print(f"[*] Summary: {valid_count}/{len(lines)} Dahl Keys are ACTIVE (100M tokens each)!")
print(f"{'='*60}\n")
