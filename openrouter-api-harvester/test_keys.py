import os, sys, time, requests, argparse

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

KEYS_FILE = os.path.join(os.path.dirname(__file__), "keys", "openrouter_keys.txt")

def test_keys(model="openrouter/free"):
    if not os.path.exists(KEYS_FILE):
        print(f"[!] Keys file not found: {KEYS_FILE}")
        return

    with open(KEYS_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not lines:
        print("[!] No keys found in openrouter_keys.txt")
        return

    print("=" * 65)
    print(f"  OPENROUTER API KEY VALIDATOR (Model: {model})")
    print(f"  Found {len(lines)} key(s) to test")
    print("=" * 65)

    valid_count = 0
    headers_base = {
        "HTTP-Referer": "https://localhost",
        "X-Title": "OpenRouter Key Validator",
        "Content-Type": "application/json"
    }

    for idx, line in enumerate(lines, 1):
        if "|" in line:
            name, key = line.split("|", 1)
        else:
            name, key = f"Key-{idx}", line

        name = name.strip()
        key = key.strip()

        print(f"\n[{idx}/{len(lines)}] Testing: {name}")
        masked_key = f"{key[:14]}...{key[-6:]}" if len(key) > 20 else key
        print(f"      Key: {masked_key}")

        headers = {**headers_base, "Authorization": f"Bearer {key}"}
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Ping test, reply 'PONG'"}],
            "max_tokens": 10
        }

        t0 = time.time()
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=20
            )
            elapsed = time.time() - t0

            if r.status_code == 200:
                data = r.json()
                choice = data.get("choices", [{}])[0]
                msg = choice.get("message", {})
                content = msg.get("content") or msg.get("reasoning") or ""
                reply = str(content).strip()
                used_model = data.get("model", model)
                print(f"      [OK] Valid | Latency: {elapsed:.2f}s | Routed to: {used_model}")
                print(f"      Response: {reply}")
                valid_count += 1
            else:
                print(f"      [FAIL] Status: {r.status_code} | Error: {r.text[:200]}")
        except Exception as e:
            print(f"      [ERROR] Connection error: {e}")

    print("\n" + "=" * 65)
    print(f"  SUMMARY: {valid_count}/{len(lines)} key(s) are WORKING")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test OpenRouter API keys")
    parser.add_argument("--model", default="openrouter/free", help="Model slug to test with (default: openrouter/free)")
    args = parser.parse_args()
    test_keys(model=args.model)
