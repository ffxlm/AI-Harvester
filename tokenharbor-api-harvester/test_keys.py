#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TokenHarbor Key Validator
Tests all keys in keys/tokenharbor_keys.txt against TokenHarbor /v1/models & free chat completions.
"""

import os
import sys
import requests

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "keys", "tokenharbor_keys.txt")

def main():
    if not os.path.exists(KEYS_FILE):
        print(f"[!] Keys file not found: {KEYS_FILE}")
        return

    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    if not lines:
        print("[!] No keys found in file.")
        return

    print("=" * 65)
    print(f"   VALIDATING {len(lines)} TOKENHARBOR API KEY(S)")
    print("=" * 65)

    valid_count = 0
    for idx, line in enumerate(lines, 1):
        parts = line.split("|")
        if len(parts) >= 2:
            email, key = parts[0], parts[1]
        else:
            email, key = f"key_{idx}", parts[0]

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }

        try:
            # 1. Check models
            r = requests.get("https://tokenharbor.ai/v1/models", headers=headers, timeout=10)
            if r.status_code == 200:
                # 2. Test free completion
                payload = {
                    "model": "deepseek-v4-flash:free",
                    "messages": [{"role": "user", "content": "ping"}]
                }
                c_res = requests.post("https://tokenharbor.ai/v1/chat/completions", headers=headers, json=payload, timeout=15)
                if c_res.status_code == 200:
                    print(f"[{idx}/{len(lines)}] [ACTIVE & READY] {email} | {key[:14]}...{key[-6:]} (DeepSeek-V4 Free OK)")
                    valid_count += 1
                else:
                    print(f"[{idx}/{len(lines)}] [MODELS OK / CHAT {c_res.status_code}] {email} | {key[:14]}...{key[-6:]}")
                    valid_count += 1
            elif r.status_code == 403:
                print(f"[{idx}/{len(lines)}] [UNVERIFIED EMAIL] {email} | {key[:14]}...{key[-6:]}")
            else:
                print(f"[{idx}/{len(lines)}] [FAILED: HTTP {r.status_code}] {email} | {key[:14]}...{key[-6:]}")
        except Exception as e:
            print(f"[{idx}/{len(lines)}] [ERROR] {email}: {e}")

    print("=" * 65)
    print(f"Validation complete: {valid_count}/{len(lines)} active keys.")
    print("=" * 65)

if __name__ == "__main__":
    main()
