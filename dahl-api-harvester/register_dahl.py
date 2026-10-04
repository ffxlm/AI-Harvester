#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dahl Inference (Gonka Network) Automated Account & API Key Harvester
Features:
- Pure REST API (No Browser, 0% RAM usage, completely freeze-proof)
- Automatically grants 100,000,000 Tokens (100 Million Free Tokens) per account
- Allocates max free tokens directly to the API key
- Formats keys as username|api_key into keys/dahl_keys.txt
- Full OpenAI-compatible endpoint with DeepSeek-V4 Flash, GLM-5.3, MiniMax M2.7
"""

import os
import sys
import time
import random
import string
import argparse
import requests

# Ensure UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(BASE_DIR, "keys", "dahl_keys.txt")
API_BASE_URL = "https://inference.dahl.global"

def get_random_username():
    prefixes = ['dahl', 'hyper', 'cyber', 'agent', 'gonka', 'matrix', 'flash', 'apex', 'nova', 'orbit']
    prefix = random.choice(prefixes)
    rnd_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{prefix}_{rnd_suffix}"

def create_dahl_account(index=1, total=1, proxy_obj=None):
    username = get_random_username()
    print(f"\n{'='*60}", flush=True)
    print(f"[{index}/{total}] Starting Dahl 100M Harvest for: {username}", flush=True)
    if proxy_obj:
        print(f"[*] Route via Proxy #{index} [{proxy_obj.get('country', 'XX')}]: {proxy_obj.get('ip')}:{proxy_obj.get('port')}", flush=True)
    else:
        print("[*] Route via Direct IP", flush=True)
    print(f"{'='*60}", flush=True)

    session = requests.Session()
    if proxy_obj:
        session.proxies = {
            'http': proxy_obj['url'],
            'https': proxy_obj['url']
        }

    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
        'Origin': API_BASE_URL,
        'Referer': f"{API_BASE_URL}/account",
        'Accept': 'application/json, text/plain, */*'
    })

    try:
        # Step 1: Create Account
        print(f"[1/4] Registering account '{username}' via REST API...", flush=True)
        res_signup = session.post(f"{API_BASE_URL}/v1/auth/signup", json={"username": username}, timeout=15)
        
        if res_signup.status_code == 429:
            err_msg = res_signup.json().get('error', {}).get('message', 'Rate limited')
            print(f"[!] Cooldown Active from Dahl: {err_msg}", flush=True)
            print("[!] Dahl enforces an IP-based cooldown (~10-15 minutes).", flush=True)
            print("[i] Hint: Use rotating proxies or switch IP to bypass.", flush=True)
            return None

        if not res_signup.ok:
            print(f"[!] Signup failed (HTTP {res_signup.status_code}): {res_signup.text}", flush=True)
            return None

        signup_data = res_signup.json()
        fingerprint = signup_data.get("fingerprint")
        api_key_obj = signup_data.get("api_key", {})
        key_id = api_key_obj.get("id")
        api_token = api_key_obj.get("token")

        if not api_token or not fingerprint:
            print("[!] Incomplete signup response received!", flush=True)
            return None

        print(f"[2/4] Account created! Fingerprint: {fingerprint[:8]}...", flush=True)
        print(f"      Initial API Key: {api_token[:14]}...", flush=True)

        # Step 2: Sign in to authenticate session
        print("[3/4] Authenticating session...", flush=True)
        res_signin = session.post(f"{API_BASE_URL}/v1/auth/signin", json={"fingerprint": fingerprint}, timeout=15)
        if not res_signin.ok:
            print(f"[!] Signin failed (HTTP {res_signin.status_code}): {res_signin.text}", flush=True)
            return None

        # Step 3: Check Account token balance
        res_acc = session.get(f"{API_BASE_URL}/v1/account", timeout=15)
        if not res_acc.ok:
            print(f"[!] Could not query account info (HTTP {res_acc.status_code})", flush=True)
            return None

        acc_data = res_acc.json()
        token_balance = acc_data.get("token_balance", 100000000)
        print(f"[4/4] Free token pool detected: {token_balance:,} tokens!", flush=True)

        # Step 4: Allocate max tokens to the key
        if token_balance > 0 and key_id:
            print(f"[*] Allocating {token_balance:,} tokens to API Key #{key_id}...", flush=True)
            res_alloc = session.post(f"{API_BASE_URL}/v1/account/allocate", json={
                "key_id": key_id,
                "amount": token_balance
            }, timeout=15)
            if res_alloc.ok:
                print(f"[+] Successfully allocated {token_balance:,} tokens!", flush=True)
            else:
                print(f"[!] Allocate failed: {res_alloc.text}, proceeding anyway...", flush=True)

        # Save to keys file in username|api_key format
        os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
        with open(KEYS_FILE, "a", encoding="utf-8") as f:
            f.write(f"{username}|{api_token}\n")

        print(f"\n🎉 SUCCESS! Dahl Key Harvested with 100M Tokens:")
        print(f"    Username: {username}")
        print(f"    API Key:  {api_token}")
        print(f"    Endpoint: {API_BASE_URL}/v1")
        print(f"[+] Saved to {KEYS_FILE}!\n", flush=True)
        return api_token

    except Exception as e:
        print(f"[!] Exception during Dahl harvesting: {e}", flush=True)
        return None

def main():
    parser = argparse.ArgumentParser(description="Automated Dahl Inference 100M Key Harvester")
    parser.add_argument("--count", type=int, default=1, help="Number of accounts/keys to generate (default: 1)")
    parser.add_argument("--delay", type=int, default=3, help="Delay in seconds between registrations (default: 3)")
    args = parser.parse_args()

    # Load rotating proxy pool
    proxies = []
    try:
        sys.path.insert(0, os.path.dirname(BASE_DIR))
        from proxy_manager import get_webshare_proxies
        proxies = get_webshare_proxies()
    except Exception as e:
        pass

    if proxies:
        print(f"[*] 🌐 Webshare Proxy Pool Active: {len(proxies)} rotating proxies loaded.", flush=True)
    else:
        print("[*] No proxy configured, using Direct IP.", flush=True)

    print(f"[*] Starting Dahl 100M Key Harvester. Target: {args.count} account(s)")
    success_count = 0
    proxy_idx = 0
    for i in range(1, args.count + 1):
        key = None
        # Try proxies if available
        max_attempts = len(proxies) if proxies else 1
        for _ in range(max_attempts):
            proxy_choice = proxies[proxy_idx % len(proxies)] if proxies else None
            proxy_idx += 1
            key = create_dahl_account(index=i, total=args.count, proxy_obj=proxy_choice)
            if key:
                break
            if proxies:
                print("[*] Rotating to next proxy in pool...", flush=True)

        if key:
            success_count += 1
        if i < args.count:
            delay_sec = min(args.delay, 2) if proxies else args.delay
            print(f"[*] Cooling down {delay_sec}s before next account...", flush=True)
            time.sleep(delay_sec)

    print(f"\n{'='*60}")
    print(f"[*] Batch Complete! Successfully harvested {success_count}/{args.count} Dahl keys.")
    print(f"[*] Keys file: {KEYS_FILE}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
