#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TokenHarbor.ai Automated Account & API Key Harvester
Features:
- Automated Signup on TokenHarbor.ai
- Human-like typing & timing simulation (bypasses speed thresholds)
- Gmail IMAP Catch-All verification link extraction & browser confirmation
- Automated 'Enable free models' consent activation
- Full API Key creation & extraction (thk_live_...)
- Bandwidth & resource optimizations (800x600, GPU disabled, background networking disabled)
- Automatic Webshare Rotating Proxy support with smart fallback
- Formats keys as email|api_key for 1-click 9Router sync
"""

import os
import sys
import time
import random
import string
import re
import imaplib
import email
import tempfile
import shutil
import argparse
import requests
from DrissionPage import ChromiumPage, ChromiumOptions
from dotenv import load_dotenv

# Ensure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
PARENT_ENV = os.path.join(PROJECT_ROOT, ".env")
LOCAL_ENV = os.path.join(BASE_DIR, ".env")

if os.path.exists(PARENT_ENV):
    load_dotenv(PARENT_ENV, override=True)
if os.path.exists(LOCAL_ENV):
    load_dotenv(LOCAL_ENV, override=True)

sys.path.append(PROJECT_ROOT)
try:
    from proxy_manager import get_webshare_proxies
except ImportError:
    get_webshare_proxies = lambda: []

GMAIL_USER = os.getenv("GMAIL_BASE_EMAIL")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD")
CUSTOM_DOMAIN = os.getenv("CUSTOM_DOMAIN", "thirx.com").strip()
KEYS_FILE = os.path.join(BASE_DIR, "keys", "tokenharbor_keys.txt")

def rand_str(length=8):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def generate_strong_password():
    return f"P@ssw0rd{rand_str(6)}!Sec"

def test_api_key(api_key):
    """Verifies that the API key is active by calling the /v1/models endpoint."""
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        res = requests.get("https://tokenharbor.ai/v1/models", headers=headers, timeout=10)
        return res.status_code == 200
    except Exception:
        return False

def get_latest_uids():
    """Returns set of all existing UID strings in Gmail INBOX to detect newly arriving mail."""
    if not GMAIL_USER or not GMAIL_PASS:
        return set()
    try:
        m = imaplib.IMAP4_SSL('imap.gmail.com')
        m.login(GMAIL_USER, GMAIL_PASS)
        m.select('INBOX')
        status, data = m.search(None, 'ALL')
        m.logout()
        if status == 'OK' and data[0]:
            return set(data[0].split())
    except Exception:
        pass
    return set()

def wait_for_verification_email(target_email, baseline_uids=None, timeout=60):
    """Waits for and extracts the verification link from Gmail IMAP."""
    start_time = time.time()
    print(f"[*] Waiting for verification email for {target_email} via IMAP...", flush=True)

    while time.time() - start_time < timeout:
        time.sleep(3)
        try:
            m = imaplib.IMAP4_SSL('imap.gmail.com')
            m.login(GMAIL_USER, GMAIL_PASS)
            m.select('INBOX')
            status, data = m.search(None, 'ALL')
            if status != 'OK' or not data[0]:
                m.logout()
                continue

            current_uids = data[0].split()
            new_uids = [u for u in current_uids if baseline_uids is None or u not in baseline_uids]
            search_uids = new_uids if new_uids else current_uids[-6:]

            for u in reversed(search_uids):
                res, md = m.fetch(u, '(RFC822)')
                if res != 'OK':
                    continue
                msg = email.message_from_bytes(md[0][1])
                to_addr = str(msg.get("To", "")).lower()
                subj = str(msg.get("Subject", "")).lower()
                body = ""

                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() in ['text/plain', 'text/html']:
                            body += str(part.get_payload(decode=True))
                else:
                    body = str(msg.get_payload(decode=True))

                if target_email.lower() in to_addr or target_email.lower() in str(msg).lower():
                    if "verify" in subj or "verify" in body.lower():
                        links = re.findall(r'https://tokenharbor\.ai/verify-email\?token=[^\s<>\"\'\)]+', body)
                        if links:
                            clean_link = links[0].replace('\\r', '').replace('\\n', '')
                            m.logout()
                            elapsed = round(time.time() - start_time, 1)
                            print(f"[+] Verification link received in {elapsed}s!", flush=True)
                            return clean_link

            m.logout()
        except Exception:
            pass

    print("[!] Verification email timed out.", flush=True)
    return None

def harvest_tokenharbor(index=1, total=1, headless=True, proxy_obj=None):
    account_email = f"th_{rand_str(8)}@{CUSTOM_DOMAIN}"
    account_pass = generate_strong_password()

    print(f"\n{'='*60}")
    print(f"[{index}/{total}] Starting TokenHarbor Harvest for: {account_email}")
    if proxy_obj:
        print(f"[*] Route via Proxy #{index} [{proxy_obj.get('country', 'XX')}]: {proxy_obj.get('ip')}:{proxy_obj.get('port')}", flush=True)
    else:
        print("[*] Route via Direct IP", flush=True)
    print(f"{'='*60}")

    baseline_uids = get_latest_uids()

    tmp_dir = tempfile.mkdtemp(prefix="tokenharbor_profile_")
    co = ChromiumOptions()
    co.set_user_data_path(tmp_dir)
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')
    # Bandwidth saving flags
    co.set_argument('--disable-background-networking')
    co.set_argument('--disable-component-update')
    co.set_argument('--disable-client-side-phishing-detection')
    co.set_argument('--disable-sync')
    co.set_argument('--disable-default-apps')
    co.set_argument('--no-first-run')
    co.set_argument('--metrics-recording-only')
    co.set_argument('--disable-features=Translate,OptimizationHints,MediaRouter,DialMediaRouteProvider')
    co.set_argument('--disable-gpu')
    if proxy_obj:
        co.set_argument(f"--proxy-server={proxy_obj['ip']}:{proxy_obj['port']}")

    if headless:
        co.set_argument('--window-position=-2400,-2400')
        co.set_argument('--window-size=800,600')

    page = None
    api_key = None

    try:
        page = ChromiumPage(co)

        # Step 1: Open direct Signup page
        print("[1/6] Navigating to https://tokenharbor.ai/login?mode=signup ...", flush=True)
        page.get("https://tokenharbor.ai/login?mode=signup")
        time.sleep(3)

        email_inp = page.ele('@name=email', timeout=10)
        pass_inp = page.ele('@name=password', timeout=10)

        if not email_inp or not pass_inp:
            print("[!] Email/password form inputs not found.", flush=True)
            return None

        # Step 2: Ensure form is in Sign up mode
        submit_btn = page.ele('xpath://button[normalize-space()="Create account"]', timeout=3)
        if not submit_btn:
            print("[2/6] Switching to 'Create an account'...", flush=True)
            create_btn = page.ele('xpath://button[contains(., "Create an account")]', timeout=5) or page.ele('xpath://a[contains(., "Create an account")]', timeout=5)
            if create_btn:
                create_btn.click()
                time.sleep(2)
            submit_btn = page.ele('xpath://button[normalize-space()="Create account"]') or page.ele('xpath://button[@type="submit"]')
        else:
            print("[2/6] Direct 'Create account' signup form active.", flush=True)

        # Step 3: Fill credentials with human-like typing simulation
        print("[3/6] Typing credentials with human delays...", flush=True)
        email_inp.click()
        time.sleep(0.3)
        for ch in account_email:
            email_inp.input(ch)
            time.sleep(random.uniform(0.03, 0.07))

        time.sleep(0.8)
        pass_inp.click()
        time.sleep(0.3)
        for ch in account_pass:
            pass_inp.input(ch)
            time.sleep(random.uniform(0.03, 0.07))

        # Wait human cooldown to avoid 'doing that a bit fast' rate threshold
        time.sleep(6)

        if submit_btn:
            submit_btn.click()
        print("[4/6] Registration form submitted. Awaiting confirmation...", flush=True)

        time.sleep(5)
        body_text = page.ele('tag:body').text
        if "bit fast" in body_text:
            print("  [*] Velocity defense triggered ('doing that a bit fast'). Cooling down 7s and resubmitting...", flush=True)
            time.sleep(7)
            retry_btn = page.ele('xpath://button[normalize-space()="Create account"]') or page.ele('xpath://button[@type="submit"]')
            if retry_btn:
                retry_btn.click()
                time.sleep(5)
            body_text = page.ele('tag:body').text

        if "not supported" in body_text:
            print("[!] Proxy IP flagged by TokenHarbor (VPN/Proxy detected).", flush=True)
            return None

        if "Too many sign-ups" in body_text or "try again in an hour" in body_text:
            print("[!] TokenHarbor Rate Limit: 'Too many sign-ups from this network. Please try again in an hour.'", flush=True)
            return None

        # Step 4: Verification link via IMAP
        verify_link = wait_for_verification_email(account_email, baseline_uids=baseline_uids, timeout=90)
        if verify_link:
            print("[5/6] Confirming email verification in browser session...", flush=True)
            page.get(verify_link)
            time.sleep(3)

            # Dismiss Enable free models modal if present
            enable_btn = page.ele('xpath://button[normalize-space()="Enable free models"]', timeout=4)
            if enable_btn:
                print("  [+] Activating 'Enable free models' consent...", flush=True)
                enable_btn.click()
                time.sleep(1.5)
        else:
            print("[!] Failed to obtain verification email.", flush=True)

        # Step 5: Navigate to API Keys page and create a key
        print("[6/6] Generating TokenHarbor API Key...", flush=True)
        page.get("https://tokenharbor.ai/dashboard/api-keys")
        time.sleep(4)

        new_key_btn = (
            page.ele('xpath://button[contains(., "New key") or contains(., "New Key")]', timeout=6)
            or page.ele('xpath://button[contains(., "Create key") or contains(., "Create Key")]', timeout=4)
            or page.ele('text:New key', timeout=4)
            or page.ele('xpath://button[contains(., "+")]', timeout=3)
        )
        if new_key_btn:
            print("  [*] Clicking new key button...", flush=True)
            new_key_btn.click()
            time.sleep(1.5)

        label_inp = page.ele('xpath://input[@name="name" or @name="label" or @placeholder]', timeout=5) or page.ele('tag:input', timeout=5)
        if label_inp:
            label_inp.input("default-key")
            time.sleep(0.5)

        create_key_btn = page.ele('xpath://button[normalize-space()="Create key" or normalize-space()="Create"]', timeout=5) or page.ele('xpath://button[@type="submit"]', timeout=3)
        if create_key_btn:
            print("  [*] Submitting key creation...", flush=True)
            try:
                create_key_btn.click()
            except Exception:
                pass
            time.sleep(3)

        # Extract thk_live_... key from page
        matches = re.findall(r'thk_live_[a-zA-Z0-9_\-]{30,}', page.html)
        if not matches:
            try:
                for el in page.eles('tag:input') + page.eles('tag:code') + page.eles('tag:span'):
                    try:
                        val = el.attr('value') or el.text or ''
                        m = re.findall(r'thk_live_[a-zA-Z0-9_\-]{30,}', val)
                        if m:
                            matches = m
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if matches:
            api_key = matches[0]
            print(f"[+] Successfully harvested API Key: {api_key[:14]}...{api_key[-6:]}", flush=True)

        if api_key:
            # Validate with live API
            print("[*] Validating API key with TokenHarbor API...", flush=True)
            is_valid = test_api_key(api_key)
            if is_valid:
                print("[+] Key verified successfully! [ACTIVE]", flush=True)
            else:
                print("[!] Key returned non-200 (TokenHarbor might be provisioning).", flush=True)

            # Save in 9Router format: email|api_key
            os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
            with open(KEYS_FILE, "a", encoding="utf-8") as f:
                f.write(f"{account_email}|{api_key}\n")
            print(f"[+] Saved key to {KEYS_FILE}", flush=True)

            return {
                "email": account_email,
                "api_key": api_key,
                "valid": is_valid
            }
        else:
            print("[!] Failed to extract API key from page.", flush=True)
            return None

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[!] Error during harvest: {e}", flush=True)
        return None
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
        time.sleep(0.5)
        shutil.rmtree(tmp_dir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Automated TokenHarbor API Key Harvester")
    parser.add_argument("--count", type=int, default=1, help="Number of API keys to harvest (default: 1)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in background")
    parser.add_argument("--use-proxy", action="store_true", default=False, help="Use Webshare rotating proxies (default: Direct IP for anti-VPN bypass)")
    args = parser.parse_args()

    if not GMAIL_USER or not GMAIL_PASS:
        print("[!] GMAIL_BASE_EMAIL and GMAIL_APP_PASSWORD must be configured in .env")
        sys.exit(1)

    print("=" * 65)
    print("   TOKENHARBOR AUTOMATED API KEY HARVESTER")
    print(f"   Target Domain  : {CUSTOM_DOMAIN}")
    print(f"   Target Count   : {args.count}")
    print(f"   Output File    : {KEYS_FILE}")
    print("=" * 65)

    proxies = get_webshare_proxies() if args.use_proxy else []
    if proxies:
        us_proxies = [p for p in proxies if p.get('country') == 'US']
        other_proxies = [p for p in proxies if p.get('country') != 'US']
        proxies = us_proxies + other_proxies
        print(f"[*] 🌐 Webshare Proxy Pool Active: {len(proxies)} rotating proxies ({len(us_proxies)} US prioritized).\n")
    else:
        print("[*] 🌐 Direct IP Mode Active (Clean residential connection for TokenHarbor).\n")

    successful_keys = []
    proxy_index = 0

    for i in range(1, args.count + 1):
        print(f"\n>>> HARVESTING ACCOUNT {i} OF {args.count} <<<")
        success = False
        max_retries = 3

        for retry in range(max_retries):
            if proxies and retry == 0:
                p_obj = proxies[proxy_index % len(proxies)]
                proxy_index += 1
            else:
                p_obj = None  # Direct IP fallback to bypass datacenter block

            result = harvest_tokenharbor(
                index=i,
                total=args.count,
                headless=args.headless,
                proxy_obj=p_obj
            )

            if result and result.get("api_key"):
                successful_keys.append(result)
                success = True
                break
            else:
                if retry < max_retries - 1:
                    print(f"[*] Retry {retry + 1}/{max_retries} with next proxy in pool...", flush=True)
                    time.sleep(3)

        if not success:
            print(f"[!] Failed to harvest account {i} after {max_retries} retries.", flush=True)

    print("\n" + "=" * 65)
    print(f"   HARVEST COMPLETED: {len(successful_keys)}/{args.count} Keys Harvested!")
    print("=" * 65)
    for k in successful_keys:
        status = "[ACTIVE]" if k["valid"] else "[UNCHECKED]"
        print(f" - {status} {k['email']} | {k['api_key'][:14]}...{k['api_key'][-6:]}")

    print(f"\nKeys saved in 9Router format at: {KEYS_FILE}\n")

if __name__ == "__main__":
    main()
