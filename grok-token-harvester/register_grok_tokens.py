import os, sys, time, random, string, re, imaplib, email, argparse, json, requests, tempfile, shutil
from DrissionPage import ChromiumPage, ChromiumOptions
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_ENV = os.path.join(os.path.dirname(SCRIPT_DIR), ".env")
LOCAL_ENV = os.path.join(SCRIPT_DIR, ".env")
if os.path.exists(PARENT_ENV):
    load_dotenv(PARENT_ENV)
if os.path.exists(LOCAL_ENV):
    load_dotenv(LOCAL_ENV, override=True)

CUSTOM_DOMAIN = os.getenv("CUSTOM_DOMAIN", "thirx.com").strip()
GMAIL_USER = os.getenv("GMAIL_BASE_EMAIL")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD")
PROXY = (os.getenv("GROK_PROXY") or "").strip()
ACCOUNTS_JSON = os.path.join(SCRIPT_DIR, "grok_accounts.json")
YESCAPTCHA_KEY = os.getenv("YESCAPTCHA_KEY", "").strip()
GROK_CF_SITEKEY = "0x4AAAAAAAhr9JGVDZbrZOo0"

def safe_run_js(page, script, retries=4, delay=1.5):
    """Executes JS safely handling temporary page refresh or context loss."""
    for i in range(retries):
        try:
            return page.run_js(script)
        except Exception as e:
            msg = str(e).lower()
            if "refreshed" in msg or "disconnected" in msg or "context" in msg:
                time.sleep(delay)
            else:
                if i == retries - 1:
                    raise e
                time.sleep(delay)
    return None

def solve_grok_turnstile(page):
    """
    Attempts to solve Turnstile verification on xAI registration:
    Requests solution from YesCaptcha and injects token + triggers React onToken callbacks.
    """
    if not YESCAPTCHA_KEY:
        print("  [!] YESCAPTCHA_KEY missing in .env, cannot solve Turnstile automatically", flush=True)
        return False

    print("  [*] Requesting Turnstile solution from YesCaptcha for xAI...", flush=True)
    try:
        req_payload = {
            "clientKey": YESCAPTCHA_KEY,
            "task": {
                "type": "TurnstileTaskProxyless",
                "websiteURL": page.url,
                "websiteKey": GROK_CF_SITEKEY
            }
        }
        r = requests.post("https://api.yescaptcha.com/createTask", json=req_payload, timeout=10).json()
        task_id = r.get("taskId")
        if not task_id:
            print(f"  [!] YesCaptcha createTask failed: {r}", flush=True)
            return False

        print(f"  [+] YesCaptcha Task ID: {task_id}, awaiting solution...", flush=True)
        for _ in range(15):
            time.sleep(3)
            res = requests.post("https://api.yescaptcha.com/getTaskResult", json={
                "clientKey": YESCAPTCHA_KEY,
                "taskId": task_id
            }, timeout=10).json()
            if res.get("status") == "ready":
                token = res.get("solution", {}).get("token")
                print(f"  [+] Turnstile solved by YesCaptcha! Token: {token[:25]}...", flush=True)
                safe_run_js(page, f'''
                    var token = "{token}";
                    // 1. Inject into hidden inputs
                    var inputs = document.querySelectorAll('[name="cf-turnstile-response"], [name="turnstile_response"], input[type="hidden"]');
                    for (var inp of inputs) {{
                        if (inp.name && inp.name.includes("turnstile")) {{
                            inp.value = token;
                            inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                    // 2. Trigger React callback via Fiber/Props (supporting onToken and onSuccess)
                    var all = document.querySelectorAll('*');
                    for (var el of all) {{
                        for (var k in el) {{
                            if (k.startsWith('__reactProps$')) {{
                                var p = el[k];
                                if (p && typeof p.onToken === 'function') {{
                                    try {{ p.onToken(token); }} catch(e){{}}
                                }}
                                if (p && typeof p.onSuccess === 'function') {{
                                    try {{ p.onSuccess(token); }} catch(e){{}}
                                }}
                                if (p && typeof p.callback === 'function') {{
                                    try {{ p.callback(token); }} catch(e){{}}
                                }}
                            }}
                            if (k.startsWith('__reactFiber$')) {{
                                var f = el[k];
                                var cur = f;
                                var d = 0;
                                while (cur && d < 8) {{
                                    if (cur.memoizedProps) {{
                                        var mp = cur.memoizedProps;
                                        if (typeof mp.onToken === 'function') {{
                                            try {{ mp.onToken(token); }} catch(e){{}}
                                        }}
                                        if (typeof mp.onSuccess === 'function') {{
                                            try {{ mp.onSuccess(token); }} catch(e){{}}
                                        }}
                                    }}
                                    cur = cur.return;
                                    d++;
                                }}
                            }}
                        }}
                    }}
                ''')
                return True
    except Exception as e:
        print(f"  [!] YesCaptcha error: {e}", flush=True)

    return False

# xAI / Grok CLI OAuth2 Constants
CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
SCOPE = "openid profile email offline_access grok-cli:access api:access conversations:read conversations:write"
DEVICE_CODE_URL = "https://auth.x.ai/oauth2/device/code"
TOKEN_URL = "https://auth.x.ai/oauth2/token"
USER_AGENT = "grok-pager/1.0.44 grok-shell/1.0.44 (linux; x86_64)"

def rand_str(length=8):
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def rand_name():
    firsts = ["Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Pat", "Riley", "Casey", "Jamie"]
    lasts = ["Smith", "Taylor", "Brown", "Wilson", "Davies", "Evans", "Thomas", "Roberts", "Johnson", "Walker"]
    return random.choice(firsts), random.choice(lasts)

def get_latest_uids():
    """Get the highest UID currently in INBOX and Spam as a baseline."""
    uids_map = {}
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(GMAIL_USER, GMAIL_PASS)
        for folder in ["INBOX", "[Gmail]/Spam"]:
            m.select(folder)
            _, d = m.uid('search', None, 'ALL')
            all_u = [int(x) for x in d[0].split()] if d and d[0] else []
            uids_map[folder] = max(all_u) if all_u else 0
        m.logout()
    except Exception as e:
        print(f"  [Baseline UID Error] {e}", flush=True)
    return uids_map

def fetch_otp(target_email, baseline_uids=None, timeout=90):
    """Wait for a NEW email addressed to target_email."""
    deadline = time.time() + timeout
    print(f"  Waiting up to {timeout}s for OTP to {target_email}...", flush=True)

    while time.time() < deadline:
        time.sleep(3)
        try:
            m = imaplib.IMAP4_SSL("imap.gmail.com")
            m.login(GMAIL_USER, GMAIL_PASS)

            for folder in ["INBOX", "[Gmail]/Spam"]:
                m.select(folder)
                base = (baseline_uids or {}).get(folder, 0)
                search_criterion = f'UID {base+1}:*' if base > 0 else 'ALL'

                _, d = m.uid('search', None, search_criterion)
                candidate_uids = [int(x) for x in d[0].split()] if d and d[0] else []
                new_uids = [u for u in candidate_uids if u > base]

                for u in reversed(new_uids):
                    _, md = m.uid('fetch', str(u).encode(), "(RFC822)")
                    msg = email.message_from_bytes(md[0][1])
                    to_addr = str(msg.get("To", "")).lower()
                    subj = str(msg.get("Subject", ""))

                    if target_email.lower() in to_addr or target_email.lower() in str(msg):
                        m_code = re.search(r"([A-Z0-9]{3})-?([A-Z0-9]{3})", subj)
                        if m_code:
                            code = m_code.group(1) + m_code.group(2)
                            print(f"  [+] Found new email UID {u} in {folder} -> OTP: {m_code.group(1)}-{m_code.group(2)}", flush=True)
                            m.logout()
                            return code
            m.logout()
        except Exception as e:
            pass

    return None

def authorize_device_code(page, target_email):
    """Requests device code and authorizes it using the currently logged-in browser session."""
    print("[*] Starting Grok CLI OAuth2 Device Authorization...", flush=True)
    req_data = {
        'client_id': CLIENT_ID,
        'scope': SCOPE,
        'referrer': 'grok-build'
    }
    req_headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json',
        'User-Agent': USER_AGENT
    }

    try:
        r = requests.post(DEVICE_CODE_URL, data=req_data, headers=req_headers, timeout=15)
        if r.status_code != 200:
            print(f"[!] Device code request failed: {r.status_code} {r.text}", flush=True)
            return None

        dev_res = r.json()
        device_code = dev_res.get('device_code')
        user_code = dev_res.get('user_code')
        verify_url = dev_res.get('verification_uri_complete')
        print(f"  [+] Device Code requested (User Code: {user_code})", flush=True)

        # Navigate to verify URL in browser
        page.get(verify_url)
        time.sleep(3)

        # Click Continue on device sign-in screen
        btn = page.ele('xpath://button[contains(text(), "Continue")]', timeout=8)
        if btn:
            try:
                btn.click(by_js=True)
            except Exception:
                pass
            time.sleep(3)

        # Click Allow / Authorize on consent screen
        allow_btn = page.ele('xpath://button[contains(text(), "Allow") or contains(text(), "Authorize") or contains(text(), "Confirm")]', timeout=6)
        if allow_btn:
            try:
                allow_btn.click(by_js=True)
            except Exception:
                pass
            time.sleep(2)

        # Poll token endpoint
        token_data = {
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
            'device_code': device_code,
            'client_id': CLIENT_ID
        }

        print("  [*] Polling for OAuth tokens from auth.x.ai...", flush=True)
        for poll in range(12):
            t_res = requests.post(TOKEN_URL, data=token_data, headers=req_headers, timeout=15)
            if t_res.status_code == 200:
                t_json = t_res.json()
                print("  [+] Received OAuth Tokens successfully!", flush=True)
                return {
                    "access_token": t_json.get("access_token"),
                    "refresh_token": t_json.get("refresh_token"),
                    "id_token": t_json.get("id_token"),
                    "email": target_email
                }
            time.sleep(3)

        print("[!] Polling for OAuth token timed out.", flush=True)
        return None

    except Exception as e:
        print(f"[!] Error in device code authorization: {e}", flush=True)
        return None

def register_and_harvest(index=1, total=1, headless=True, proxy_obj=None):
    tag = f"grok_{rand_str(8)}"
    reg_email = f"{tag}@{CUSTOM_DOMAIN}"
    password = f"P@ssw0rd{rand_str(6)}!"
    first_name, last_name = rand_name()

    print(f"\n[{index}/{total}] ==========================================")
    print(f"[*] Starting Grok Registration & Token Harvest:")
    print(f"    Email: {reg_email}")
    print(f"    Name:  {first_name} {last_name}")
    if proxy_obj:
        print(f"[*] Route via Proxy #{index} [{proxy_obj.get('country', 'XX')}]: {proxy_obj.get('ip')}:{proxy_obj.get('port')}", flush=True)
    elif PROXY:
        print(f"[*] Route via Configured Proxy: {PROXY}", flush=True)
    else:
        print("[*] Route via Direct IP", flush=True)
    print(f"==========================================")

    baseline_uids = get_latest_uids()

    tmp_dir = tempfile.mkdtemp(prefix="grok_profile_")
    co = ChromiumOptions()
    co.set_user_data_path(tmp_dir)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-blink-features=AutomationControlled")
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
    if headless:
        co.set_argument('--window-position=-2400,-2400')
        co.set_argument('--window-size=800,600')
    if proxy_obj:
        co.set_argument(f"--proxy-server={proxy_obj['ip']}:{proxy_obj['port']}")
    elif PROXY:
        proxy_addr = PROXY.replace("http://", "").replace("https://", "")
        co.set_argument(f"--proxy-server={proxy_addr}")

    page = None
    try:
        page = ChromiumPage(co)

        # 1. Open Sign-up page
        print("[1/5] Opening https://accounts.x.ai/sign-up?redirect=grok-com ...", flush=True)
        page.get("https://accounts.x.ai/sign-up?redirect=grok-com")
        time.sleep(3)

        # 2. Click email registration
        print("[2/5] Selecting email registration...", flush=True)
        page.run_js('''
            for (var b of document.querySelectorAll('button, [role="button"]')) {
                if ((b.innerText || '').toLowerCase().includes('email') || (b.innerText || '').includes('อีเมล')) {
                    b.click();
                    break;
                }
            }
        ''')
        time.sleep(2)

        # 3. Input email and submit
        email_inp = page.ele('tag:input@type=email', timeout=6) or page.ele('tag:input', timeout=6)
        if not email_inp:
            print("[!] Email input not found!", flush=True)
            return None

        email_inp.input(reg_email)
        time.sleep(1)

        page.run_js('''
            for (var b of document.querySelectorAll('button')) {
                if ((b.innerText || '').trim().toLowerCase() === 'continue' || b.type === 'submit') {
                    b.click(); break;
                }
            }
        ''')
        print("[3/5] Submitted email, waiting for OTP from Gmail...", flush=True)

        code = fetch_otp(reg_email, baseline_uids=baseline_uids, timeout=90)
        if not code:
            print("[!] OTP timed out!", flush=True)
            return None

        # 4. Input OTP code
        print("[4/5] Entering OTP code into form...", flush=True)
        otp_input = page.ele('css:input[data-input-otp="true"]', timeout=6) or page.ele('css:input[name="code"]', timeout=6)
        if otp_input:
            otp_input.click()
            time.sleep(0.5)
            otp_input.input(code)

        time.sleep(2)
        page.run_js('''
            for (var b of document.querySelectorAll('button')) {
                var t = (b.innerText || '').toLowerCase();
                if (t.includes('confirm') || t.includes('continue') || b.type === 'submit') {
                    b.click();
                    break;
                }
            }
        ''')
        time.sleep(4)

        # 5. Fill Profile Details (givenName, familyName, password)
        print("[5/5] Completing profile details...", flush=True)
        gn = page.ele('#givenName', timeout=10)
        fn = page.ele('#familyName', timeout=10)
        pw = page.ele('#password', timeout=10)

        if gn: gn.input(first_name)
        time.sleep(0.2)
        if fn: fn.input(last_name)
        time.sleep(0.2)
        if pw: pw.input(password)
        time.sleep(0.3)

        # Dispatch native React events for React-Hook-Form
        safe_run_js(page, f'''
            function setNative(sel, val) {{
                var el = document.querySelector(sel);
                if (!el) return;
                el.focus();
                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(el, val);
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
            }}
            setNative('#givenName', "{first_name}");
            setNative('#familyName', "{last_name}");
            setNative('#password', "{password}");
        ''')
        time.sleep(1)

        # Solve Cloudflare Turnstile on profile form
        print("  [*] Solving Cloudflare Turnstile on profile form via YesCaptcha...", flush=True)
        solve_grok_turnstile(page)
        time.sleep(2)

        # Submit form
        print("  [*] Submitting profile form...", flush=True)
        for _ in range(8):
            submitted = safe_run_js(page, '''
                var form = document.querySelector('form');
                if (form) {
                    if (typeof form.requestSubmit === 'function') {
                        try { form.requestSubmit(); return true; } catch(e){}
                    }
                }
                for (var b of document.querySelectorAll('button')) {
                    var t = (b.innerText || '').toLowerCase();
                    if ((t.includes('complete') || t.includes('sign up') || t.includes('continue') || b.type === 'submit') && !b.disabled) {
                        b.click();
                        return true;
                    }
                }
                return false;
            ''')
            if submitted:
                break
            time.sleep(1)

        # Wait for redirect away from sign-up form
        redirected = False
        for _ in range(15):
            time.sleep(1)
            if '/sign-up' not in page.url:
                redirected = True
                break

        if not redirected:
            err_msg = safe_run_js(page, '''
                var msgs = [];
                for (var el of document.querySelectorAll('[role="alert"], p')) {
                    var txt = (el.innerText || '').trim();
                    if (txt) msgs.push(txt);
                }
                return msgs.slice(0, 5);
            ''')
            print(f"  [!] Notice: URL still on /sign-up ({page.url}). Messages on page: {err_msg}", flush=True)
        else:
            print(f"[+] Registration completed! Redirected to: {page.url}", flush=True)

        # 6. Authorize Device Code & Extract Tokens
        tokens = authorize_device_code(page, reg_email)
        if tokens:
            # Append to grok_accounts.json
            existing_data = []
            if os.path.exists(ACCOUNTS_JSON):
                try:
                    with open(ACCOUNTS_JSON, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, list):
                            existing_data = loaded
                except Exception:
                    pass

            existing_data.append(tokens)
            with open(ACCOUNTS_JSON, "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2)

            print(f"[🎉] Successfully added {reg_email} to {ACCOUNTS_JSON}")
            return tokens
        else:
            print("[!] Failed to obtain tokens for account.", flush=True)
            return None

    except Exception as e:
        print(f"[!] Exception during registration: {e}", flush=True)
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
    parser = argparse.ArgumentParser(description="Grok CLI / 9Router Automated Token Harvester")
    parser.add_argument("--count", type=int, default=1, help="Number of accounts to harvest (default: 1)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in background")
    args = parser.parse_args()

    if not GMAIL_USER or not GMAIL_PASS:
        print("[!] GMAIL_BASE_EMAIL and GMAIL_APP_PASSWORD must be configured in .env")
        sys.exit(1)

    print("=" * 65)
    print("   GROK CLI / 9ROUTER AUTOMATED TOKEN HARVESTER 🚀")
    print(f"   Target Domain  : {CUSTOM_DOMAIN}")
    print(f"   Target Count   : {args.count}")
    print(f"   Output JSON    : {ACCOUNTS_JSON}")
    print("=" * 65)

    # Load rotating proxy pool
    proxies = []
    try:
        sys.path.insert(0, os.path.dirname(SCRIPT_DIR))
        from proxy_manager import get_webshare_proxies, ensure_ip_authorized
        ensure_ip_authorized()
        proxies = get_webshare_proxies()
    except Exception:
        pass

    if proxies:
        print(f"[*] 🌐 Webshare Proxy Pool Active: {len(proxies)} rotating proxies loaded.", flush=True)
    elif PROXY:
        print(f"[*] 🌐 Using Configured Proxy: {PROXY}", flush=True)
    else:
        print("[*] No proxy configured, using Direct IP.", flush=True)

    harvested = []
    for i in range(1, args.count + 1):
        proxy_choice = proxies[(i - 1) % len(proxies)] if proxies else None
        res = register_and_harvest(i, args.count, headless=args.headless, proxy_obj=proxy_choice)
        if res:
            harvested.append(res)
        if i < args.count:
            delay_sec = 2 if proxies else 4
            print(f"[*] Cooling down {delay_sec}s before next account...", flush=True)
            time.sleep(delay_sec)

    print("\n" + "=" * 65)
    print(f"   HARVEST COMPLETED: {len(harvested)}/{args.count} Accounts Harvested!")
    print("=" * 65)
    for acc in harvested:
        print(f" - {acc['email']} | Access: {acc['access_token'][:15]}... | Refresh: {acc['refresh_token'][:15]}...")

    print(f"\n[+] File ready for 1-click import into 9Router:")
    print(f"    {ACCOUNTS_JSON}")

if __name__ == "__main__":
    main()
