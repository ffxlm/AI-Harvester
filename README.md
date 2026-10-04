# 🚀 AI-Harvester Suite

**AI-Harvester Suite** is an automated multi-provider AI account registration, token harvesting, and unified management engine. It features automated Cloudflare Turnstile solving, Gmail IMAP catch-all verification, optional Webshare rotating proxy pools, low-bandwidth browser optimizations, and seamless 1-click synchronization into [9Router](https://github.com/thirx/9router).

---

## ⚡ Supported Providers & Capabilities

| Provider | Method | Free Quota / Allowance | Supported Models / Access | Proxy Recommendation |
| :--- | :---: | :---: | :---: | :---: |
| **🌐 Dahl (Gonka)** | **Pure REST API** (~1.2s) | **100,000,000 Tokens** | `DeepSeek-V4-Flash`, `GLM-5.3-Flash`, `MiniMax-M2.7` | Direct IP / Webshare Proxy |
| **⚓ TokenHarbor** | **Headless DrissionPage** | **~150–200 Req/Week** (Rolling) | `deepseek-v4-flash:free`, `qwen3.8-flash:free`, `minimax` | **Strictly Direct Residential IP** (Blocks VPN/Proxy) |
| **⚡ OpenRouter** | **Headless DrissionPage** | **100 Req/Day/Key** | `openrouter/free`, `llama-3.3-70b:free`, `deepseek-r1:free` | Direct IP / Residential Proxy |
| **🤖 xAI Grok CLI** | **Headless DrissionPage** | **xAI Native Session** | `grok-4.7`, `grok-4.7-xhigh`, Grok Code | Direct IP / Clean Proxy |

---

## 📁 Project Structure

```text
account_generate/
├── dashboard.py                  # Real-Time Web Dashboard & 9Router Sync API (port 5050)
├── proxy_manager.py              # Webshare Rotating Proxy Pool Manager
├── requirements.txt              # Python Dependencies
├── start.sh                      # One-click startup script (Dashboard + Browser UI)
├── stop.sh                       # One-click stop script (kills dashboard and workers)
├── .env.example                  # Environment configuration template
│
├── dahl-api-harvester/           # 1. Dahl Inference 100M Token Harvester
│   ├── register_dahl.py          # Harvester script
│   ├── test_keys.py              # Key validation & latency tester
│   └── keys/dahl_keys.txt        # Stored API keys (username|api_key)
│
├── tokenharbor-api-harvester/    # 2. TokenHarbor.ai Harvester
│   ├── register_tokenharbor.py   # Harvester script
│   ├── test_keys.py              # Key validation & models tester
│   └── keys/                     # Stored keys and account credentials
│       ├── tokenharbor_keys.txt
│       └── tokenharbor_accounts.txt
│
├── openrouter-api-harvester/     # 3. OpenRouter API Key Harvester
│   ├── register_openrouter.py    # Harvester script
│   ├── test_keys.py              # Key validation & completion tester
│   └── keys/openrouter_keys.txt  # Stored API keys (email|api_key)
│
└── grok-token-harvester/         # 4. Grok xAI CLI Token Harvester
    ├── register_grok_tokens.py   # Harvester script (Turnstile + OAuth2 Device Code)
    ├── test_grok_tokens.py       # Token validation & auto-refresh tester
    └── grok_accounts.json        # Stored OAuth2 token objects (access, refresh, id_token)
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10+
- Google Chrome or Chromium
- Gmail account with an **App Password** and custom domain forwarding (Catch-All)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```

Key environment configurations:
| Variable | Description |
| :--- | :--- |
| `GMAIL_BASE_EMAIL` | Gmail address receiving forwarded catch-all emails |
| `GMAIL_APP_PASSWORD` | Google 16-character App Password for IMAP access |
| `CUSTOM_DOMAIN` | Domain for generated accounts (e.g. `thirx.com`) |
| `YESCAPTCHA_KEY` | YesCaptcha client key for Cloudflare Turnstile bypass |
| `WEBSHARE_API_KEY` | *(Optional)* Webshare API token. Leave empty to use Direct Machine IP |
| `GROK_PROXY` | *(Optional)* Static custom proxy URL (e.g. `http://user:pass@ip:port`) |
| `ROUTER_BASE_URL` | 9Router instance URL (e.g. `https://api.yourdomain.com`) |
| `ROUTER_PASSWORD` | 9Router admin access password |

---

## 🌐 Network & Proxy Architecture

- **Direct IP (Default & Recommended):**
  - If `WEBSHARE_API_KEY` is not set in `.env`, the system automatically routes all requests via your local network.
  - On residential or 4G/5G mobile SIM networks (e.g. TrueMove H), Cloudflare Turnstile passes naturally in 0 seconds and TokenHarbor anti-bot checks pass without warning.
  - To rotate IP on a 4G/5G SIM router: Simply reboot the router or reconnect cellular WAN to obtain a fresh public IP.
- **Webshare Proxy Pool (Optional):**
  - If `WEBSHARE_API_KEY` is provided, `proxy_manager.py` fetches, caches (2 hours), and rotates proxies across accounts, automatically authorizing your machine's public IP.

---

## 🚀 Usage

### Option A: Launch Web Dashboard (Recommended)
```bash
./start.sh
```
Open **`http://localhost:5050`** in your browser to view accounts, run automated harvests, and sync credentials to 9Router.

To stop the dashboard:
```bash
./stop.sh
```

---

### Option B: CLI Direct Execution

#### 1. Dahl (Gonka) Harvester
```bash
# Generate 5 keys (100M tokens each)
python3 dahl-api-harvester/register_dahl.py --count 5

# Test stored keys
python3 dahl-api-harvester/test_keys.py
```

#### 2. TokenHarbor Harvester
```bash
# Generate 1 account & API key
python3 tokenharbor-api-harvester/register_tokenharbor.py --count 1

# Test stored keys against /v1/models and free completions
python3 tokenharbor-api-harvester/test_keys.py
```

#### 3. OpenRouter Harvester
```bash
# Generate 1 account & API key
python3 openrouter-api-harvester/register_openrouter.py --count 1

# Test stored keys
python3 openrouter-api-harvester/test_keys.py
```

#### 4. xAI Grok CLI Harvester
```bash
# Generate 1 account & capture OAuth2 CLI tokens
python3 grok-token-harvester/register_grok_tokens.py --count 1

# Test stored tokens with auto-refresh mechanism
python3 grok-token-harvester/test_grok_tokens.py
```

---

## 🔒 Security & Privacy Notice
All generated credentials (`*.txt`, `keys/`, `grok_accounts.json`, `.env`) are strictly excluded in `.gitignore` to prevent any sensitive data leakage.

---

## 📜 License
MIT License. For educational and research purposes only.
