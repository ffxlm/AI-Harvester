import os, sys, time, imaplib, email, re, random, string, argparse, tempfile, shutil, requests
from DrissionPage import ChromiumPage, ChromiumOptions
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

# Load configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_ENV = os.path.join(os.path.dirname(BASE_DIR), ".env")
LOCAL_ENV = os.path.join(BASE_DIR, ".env")
if os.path.exists(PARENT_ENV):
    load_dotenv(PARENT_ENV)
if os.path.exists(LOCAL_ENV):
    load_dotenv(LOCAL_ENV, override=True)

GMAIL_USER = os.getenv("GMAIL_BASE_EMAIL")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD")
CUSTOM_DOMAIN = os.getenv("CUSTOM_DOMAIN", "thirx.com")
KEYS_FILE = os.path.join(BASE_DIR, "keys", "openrouter_keys.txt")

def generate_random_email():
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"openrouter_{rnd}@{CUSTOM_DOMAIN}"

def generate_password():
    return "P@ssw0rdOpenRouter2026!"

def fetch_verify_link(target_email, max_wait_sec=60):
    start_time = time.time()
    print(f"[*] Waiting for verification email for {target_email} via IMAP...", flush=True)

    while time.time() - start_time < max_wait_sec:
        time.sleep(3)
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(GMAIL_USER, GMAIL_PASS)
            mail.select("inbox")

            status, msgs = mail.search(None, 'ALL')
            if not msgs or not msgs[0]:
                mail.logout()
                continue

            msg_ids = msgs[0].split()
            # Check the 10 most recent messages
            for mid in reversed(msg_ids[-10:]):
                status, data = mail.fetch(mid, '(RFC822)')
                if not data or not data[0]:
                    continue

                msg = email.message_from_bytes(data[0][1])
                to_addr = msg.get("To", "")

                if target_email.lower() in to_addr.lower():
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                body += part.get_payload(decode=True).decode('utf-8', errors='replace')
                    else:
                        body = msg.get_payload(decode=True).decode('utf-8', errors='replace')

                    links = re.findall(r'https://clerk\.openrouter\.ai/v1/verify[^\s<>"\'\)]+', body)
                    if links:
                        verify_link = links[0].replace("&amp;", "&")
                        mail.logout()
                        print(f"[+] Verification link received in {time.time() - start_time:.1f}s!", flush=True)
                        return verify_link

            mail.logout()
        except Exception as e:
            time.sleep(1)

    print("[!] Verification email timed out.", flush=True)
    return None

def test_api_key(api_key):
    """Quickly tests if the newly harvested key is valid."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "OpenRouter Harvester",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=20)
        return r.status_code == 200
    except Exception:
        return False

def register_one_account(index=1, total=1, headless=True, proxy_obj=None):
    account_email = generate_random_email()
    account_pass = generate_password()
    print(f"\n{'='*60}")
    print(f"[{index}/{total}] Starting OpenRouter Harvest for: {account_email}")
    if proxy_obj:
        print(f"[*] Route via Proxy #{index} [{proxy_obj.get('country', 'XX')}]: {proxy_obj.get('ip')}:{proxy_obj.get('port')}", flush=True)
    else:
        print("[*] Route via Direct IP", flush=True)
    print(f"{'='*60}")

    tmp_dir = tempfile.mkdtemp(prefix="openrouter_profile_")
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
    co.set_argument('--blink-settings=imagesEnabled=false')
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

        # Step 1: Open Sign Up page
        print("[1/6] Navigating to https://openrouter.ai/sign-up ...", flush=True)
        page.get("https://openrouter.ai/sign-up")
        time.sleep(2)

        # Wait for email input
        email_inp = page.ele('@name=emailAddress', timeout=15)
        if not email_inp:
            print("[!] Email input not found. Page might have blocked or redirected.", flush=True)
            return None

        email_inp.input(account_email)
        pass_inp = page.ele('@name=password', timeout=5)
        if pass_inp:
            pass_inp.input(account_pass)

        # Accept terms checkbox via React event dispatch
        page.run_js('''
            var chk = document.querySelector('input[name="legalAccepted"]');
            if (chk) {
                chk.click();
                chk.checked = true;
                chk.dispatchEvent(new Event('input', { bubbles: true }));
                chk.dispatchEvent(new Event('change', { bubbles: true }));
            }
        ''')
        time.sleep(0.5)

        # Click submit
        page.run_js('''
            var btn = document.querySelector('button[type="submit"]');
            if (btn) btn.click();
        ''')
        print("[2/6] Sign-up form submitted. Waiting for verification screen...", flush=True)

        # Wait for verify-email-address URL
        for _ in range(25):
            time.sleep(1)
            if "/verify-email-address" in page.url:
                break

        # Step 2: Fetch IMAP magic link
        print("[3/6] Fetching magic link from Gmail IMAP...", flush=True)
        verify_link = fetch_verify_link(account_email, max_wait_sec=60)
        if not verify_link:
            return None

        # Step 3: Open magic link in second tab to verify session
        print("[4/6] Authenticating via cross-tab verification...", flush=True)
        tab2 = page.new_tab(verify_link)
        time.sleep(5)
        try:
            tab2.close()
        except Exception:
            pass

        # Step 4: Navigate Tab 1 to Keys page
        print("[5/6] Navigating to API Keys page...", flush=True)
        page.get("https://openrouter.ai/keys")
        time.sleep(4)

        # Step 5: Check for onboarding modal & API Key
        print("[6/6] Checking for generated API Key...", flush=True)
        time.sleep(3)
        for step in range(12):
            # Check if key is already displayed in DOM
            matches = re.findall(r'sk-or-v1-[a-f0-9]{64}', page.html)
            if matches:
                api_key = matches[0]
                print(f"[+] Found initial workspace API key from DOM: {api_key[:14]}...{api_key[-6:]}", flush=True)
                break

            clicked_any = False
            for text_pat in ["Next", "Continue", "Get started", "Done", "Skip"]:
                btn = page.ele(f'xpath://button[contains(normalize-space(), "{text_pat}")]', timeout=2)
                if btn and btn.states.is_displayed:
                    print(f"      Proceeding onboarding step: '{btn.text}'")
                    btn.click(by_js=True)
                    time.sleep(2)
                    clicked_any = True
                    break

            if not clicked_any and step >= 3:
                break

        # If not found during onboarding, try creating one manually via 'New Key' button
        if not api_key:
            # Check once more in case DOM updated
            matches = re.findall(r'sk-or-v1-[a-f0-9]{64}', page.html)
            if matches:
                api_key = matches[0]
                print(f"[+] Found workspace API key from DOM: {api_key[:14]}...{api_key[-6:]}", flush=True)
            else:
                print("[*] Creating key via 'New Key' button...", flush=True)
                new_key_btn = page.ele('xpath://button[contains(normalize-space(), "New Key") or contains(normalize-space(), "Create Key")]', timeout=5)
                if new_key_btn:
                    new_key_btn.click(by_js=True)
                    time.sleep(2)

                    name_inp = page.ele('@name=name', timeout=5)
                    if name_inp:
                        name_inp.input("OpenRouterBot")
                        time.sleep(0.5)

                    # 1. Handle Expiration Dropdown
                    try:
                        page.run_js('''
                            for (var b of document.querySelectorAll('button, [role="combobox"]')) {
                                if ((b.innerText || '').includes('Select expiration') || (b.innerText || '').includes('expiration')) {
                                    b.click();
                                    break;
                                }
                            }
                        ''')
                        time.sleep(1)
                        no_exp = page.ele('xpath://*[contains(normalize-space(), "No expiration")]', timeout=3)
                        if no_exp:
                            no_exp.click(by_js=True)
                            time.sleep(0.5)
                    except Exception:
                        pass

                    # 2. Handle Credit Limit Dropdown
                    try:
                        page.run_js('''
                            for (var b of document.querySelectorAll('button, [role="combobox"]')) {
                                if ((b.innerText || '').includes('Choose a credit limit') || (b.innerText || '').includes('credit limit')) {
                                    b.click();
                                    break;
                                }
                            }
                        ''')
                        time.sleep(1)
                        no_limit = page.ele('xpath://*[contains(normalize-space(), "No limit")]', timeout=3)
                        if no_limit:
                            no_limit.click(by_js=True)
                            time.sleep(0.5)
                    except Exception:
                        pass

                    create_btn = page.ele('xpath://button[normalize-space()="Create"]', timeout=5)
                    if create_btn:
                        create_btn.click(by_js=True)
                        time.sleep(3)

                    matches = re.findall(r'sk-or-v1-[a-f0-9]{64}', page.html)
                    if matches:
                        api_key = matches[0]
                        print(f"[+] Successfully generated API key: {api_key[:14]}...{api_key[-6:]}", flush=True)

        if api_key:
            # Validate key with live API
            print("[*] Validating API key with OpenRouter API...", flush=True)
            is_valid = test_api_key(api_key)
            if is_valid:
                print(f"[+] Key verified successfully! [ACTIVE]", flush=True)
            else:
                print(f"[!] Key ping returned non-200 (OpenRouter might be provisioning).", flush=True)

            # Save to keys file in 9Router format: name|key
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
            print("[!] Failed to locate or generate API key.", flush=True)
            err_img = os.path.join(BASE_DIR, "keys", f"err_{account_email}.png")
            page.get_screenshot(path=err_img)
            print(f"[!] Error screenshot saved to {err_img}", flush=True)
            return None

    except Exception as e:
        print(f"[!] Error during harvest: {e}", flush=True)
        return None
    finally:
        if page:
            try:
                page.quit()
            except Exception:
                pass
        time.sleep(1)
        shutil.rmtree(tmp_dir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="Automated OpenRouter API Key Harvester")
    parser.add_argument("--count", type=int, default=1, help="Number of API keys to harvest (default: 1)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in background")
    args = parser.parse_args()

    if not GMAIL_USER or not GMAIL_PASS:
        print("[!] GMAIL_BASE_EMAIL and GMAIL_APP_PASSWORD must be configured in .env")
        sys.exit(1)

    print("=" * 65)
    print("   OPENROUTER AUTOMATED API KEY HARVESTER")
    print(f"   Target Domain  : {CUSTOM_DOMAIN}")
    print(f"   Target Count   : {args.count}")
    print(f"   Output File    : {KEYS_FILE}")
    print("=" * 65)

    # Load rotating proxy pool
    proxies = []
    try:
        sys.path.insert(0, os.path.dirname(BASE_DIR))
        from proxy_manager import get_webshare_proxies, ensure_ip_authorized
        ensure_ip_authorized()
        proxies = get_webshare_proxies()
    except Exception:
        pass

    if proxies:
        print(f"[*] 🌐 Webshare Proxy Pool Active: {len(proxies)} rotating proxies loaded.", flush=True)
    else:
        print("[*] No proxy configured, using Direct IP.", flush=True)

    harvested = []
    for i in range(1, args.count + 1):
        print(f"\n>>> HARVESTING ACCOUNT {i} OF {args.count} <<<")
        proxy_choice = proxies[(i - 1) % len(proxies)] if proxies else None
        result = register_one_account(index=i, total=args.count, headless=args.headless, proxy_obj=proxy_choice)
        if result:
            harvested.append(result)
        if i < args.count:
            delay_sec = 2 if proxies else 4
            print(f"[*] Cooling down {delay_sec}s before next account...", flush=True)
            time.sleep(delay_sec)

    print("\n" + "=" * 65)
    print(f"   HARVEST COMPLETED: {len(harvested)}/{args.count} Keys Harvested!")
    print("=" * 65)
    for res in harvested:
        status_str = "ACTIVE" if res.get('valid') else "CREATED"
        print(f" - [{status_str}] {res['email']} | {res['api_key'][:14]}...{res['api_key'][-6:]}")
    print(f"\nKeys saved in 9Router format at: {KEYS_FILE}")

if __name__ == "__main__":
    main()
