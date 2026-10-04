import os, sys, json, requests, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

ACCOUNTS_FILE = os.path.join(os.path.dirname(__file__), "grok_accounts.json")
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
USER_AGENT = "grok-pager/1.0.44 grok-shell/1.0.44 (linux; x86_64)"

def test_tokens():
    if not os.path.exists(ACCOUNTS_FILE):
        print(f"[!] File not found: {ACCOUNTS_FILE}")
        return

    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
        try:
            accounts = json.load(f)
        except Exception as e:
            print(f"[!] Error parsing JSON: {e}")
            return

    if not accounts:
        print("[!] No accounts found in grok_accounts.json")
        return

    print("=" * 65)
    print("   GROK CLI / 9ROUTER TOKEN VALIDATOR (WITH AUTO-REFRESH)")
    print(f"   Found {len(accounts)} account(s) to test")
    print("=" * 65)

    valid_count = 0
    updated = False
    for idx, acc in enumerate(accounts, 1):
        email_addr = acc.get("email", f"Account-{idx}")
        access_tok = acc.get("access_token", "")
        refresh_tok = acc.get("refresh_token", "")

        print(f"\n[{idx}/{len(accounts)}] Testing: {email_addr}")
        masked_tok = f"{access_tok[:15]}...{access_tok[-6:]}" if len(access_tok) > 25 else access_tok
        print(f"      Access Token: {masked_tok}")

        headers = {
            "Authorization": f"Bearer {access_tok}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
            "x-xai-token-auth": "xai-grok-cli",
            "x-grok-client-version": "1.0.44"
        }

        t0 = time.time()
        try:
            r = requests.get("https://cli-chat-proxy.grok.com/v1/user", headers=headers, timeout=12)
            elapsed = time.time() - t0
            
            # If expired, auto-refresh via refresh_token
            if r.status_code == 401 and refresh_tok:
                print("      [i] Access token expired. Auto-refreshing via refresh_token...")
                ref_res = requests.post("https://auth.x.ai/oauth2/token", data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_tok,
                    "client_id": CLIENT_ID
                }, headers={"User-Agent": USER_AGENT}, timeout=12)
                
                if ref_res.ok:
                    ref_data = ref_res.json()
                    acc["access_token"] = ref_data.get("access_token")
                    if ref_data.get("refresh_token"):
                        acc["refresh_token"] = ref_data.get("refresh_token")
                    updated = True
                    headers["Authorization"] = f"Bearer {acc['access_token']}"
                    r = requests.get("https://cli-chat-proxy.grok.com/v1/user", headers=headers, timeout=12)
                    elapsed = time.time() - t0

            if r.status_code == 200:
                u_data = r.json()
                has_code = u_data.get("hasGrokCodeAccess", False)
                name = f"{u_data.get('firstName', '')} {u_data.get('lastName', '')}".strip()
                print(f"      [OK] Valid | Latency: {elapsed:.2f}s | Name: {name} | GrokCode: {has_code}")
                valid_count += 1
            else:
                print(f"      [FAIL] Status: {r.status_code} | Error: {r.text[:150]}")
        except Exception as e:
            print(f"      [ERROR] Network error: {e}")

    if updated:
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(accounts, f, indent=2)
        print("\n[+] Updated fresh tokens in grok_accounts.json")

    print("\n" + "=" * 65)
    print(f"   SUMMARY: {valid_count}/{len(accounts)} Token(s) are ACTIVE and VALID!")
    print("=" * 65)

if __name__ == "__main__":
    test_tokens()
