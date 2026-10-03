# 🚀 AI-Harvester

**AI-Harvester** is an automated multi-provider AI account registration, token harvesting, and unified management engine. It features automated Cloudflare Turnstile solving, Gmail IMAP catch-all verification, Webshare rotating proxy pools, low-bandwidth browser optimizations, and seamless 1-click synchronization into [9Router](https://github.com/thirx/9router).

---

## ✨ Features

- **🌐 Dahl Inference (Gonka Network)**
  - Pure REST API architecture (zero browser overhead, lightning-fast execution).
  - Automatically provisions **100,000,000 free tokens** per account.
  - Grants access to DeepSeek-V4 Flash, GLM-5.3, and MiniMax M2.7 OpenAI-compatible endpoints.

- **⚡ OpenRouter**
  - Fully automated registration & email verification via custom domain catch-all.
  - Automatic onboarding modal dismissal and initial workspace API key harvesting.
  - Headless image-suppression mode for maximum efficiency.

- **🤖 Grok xAI CLI**
  - Automated signup on `accounts.x.ai` with Cloudflare Turnstile bypass (via YesCaptcha).
  - Automated OAuth2 Device Code flow authorization.
  - Extracts full credential sets (`access_token`, `refresh_token`, `id_token`) ready for Grok CLI & 9Router.

- **⚓ TokenHarbor.ai**
  - Automated account creation with human-like typing simulation to bypass strict anti-bot velocity defenses.
  - Automatic email verification link extraction & browser session activation via Gmail IMAP.
  - Activates free access to **DeepSeek-V4 Flash**, **Qwen-3.8 Flash**, and **MiniMax MiMo-v2.6**.
  - Direct 1-click sync to 9Router under native `provider: "tokenharbor"`.

- **⚡ High-Efficiency Bandwidth & Resource Optimization**
  - **~85% Bandwidth Reduction:** Google background networking, component updates, and safe browsing downloads are strictly suppressed.
  - **Memory & CPU Friendly:** Compact `800x600` viewport reduces framebuffer rasterization by 58%; GPU hardware acceleration is disabled to eliminate VRAM usage.
  - **Ephemeral Temp Profiles:** Each run operates inside an isolated temporary directory that is automatically destroyed on completion.

- **🛡️ Webshare Rotating Proxy Pool**
  - Integrated with Webshare API v2.
  - Automatic outbound IP authorization & smart fallback.
  - Cycles proxies across accounts to ensure 0% rate-limiting and ban avoidance.

- **☁️ 9Router 1-Click Sync**
  - Direct integration with 9Router management APIs.
  - One-click syncing for Dahl, OpenRouter, TokenHarbor, and Grok CLI bulk imports (`/api/oauth/grok-cli/bulk-import`).

- **📊 Modern Web Dashboard**
  - Built-in monitoring dashboard on `http://localhost:5050`.
  - Live proxy health status, harvested account statistics, and interactive trigger buttons.

---

## 📁 Project Structure

```text
AI-Harvester/
├── dashboard.py                  # Web Dashboard & 9Router Sync API
├── proxy_manager.py              # Webshare Proxy Pool Manager
├── requirements.txt              # Python Dependencies
├── start.sh                      # One-click startup script
├── .env.example                  # Environment template
│
├── dahl-api-harvester/           # Dahl Inference 100M Token Harvester
│   ├── register_dahl.py
│   ├── test_keys.py
│   └── keys/dahl_keys.txt
│
├── openrouter-api-harvester/     # OpenRouter API Key Harvester
│   ├── register_openrouter.py
│   ├── test_keys.py
│   └── keys/openrouter_keys.txt
│
├── grok-token-harvester/         # Grok xAI CLI Harvester
│   ├── register_grok_tokens.py
│   ├── test_grok_tokens.py
│   └── grok_accounts.json
│
└── tokenharbor-api-harvester/    # TokenHarbor.ai Harvester
    ├── register_tokenharbor.py
    ├── test_keys.py
    └── keys/tokenharbor_keys.txt
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites
- Python 3.10+
- Google Chrome / Chromium installed
- Domain configured with Gmail Catch-All forwarding

### 2. Install Dependencies
```bash
git clone https://github.com/ffxlm/AI-Harvester.git
cd AI-Harvester
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
| `GMAIL_APP_PASSWORD` | Google App Password for IMAP access |
| `CUSTOM_DOMAIN` | Target domain for account generation (e.g. `thirx.com`) |
| `YESCAPTCHA_KEY` | YesCaptcha client key for Turnstile solving |
| `WEBSHARE_API_KEY` | Webshare API token for rotating proxy pool |
| `ROUTER_BASE_URL` | 9Router instance URL (e.g. `https://api.yourdomain.com`) |
| `ROUTER_PASSWORD` | 9Router admin access password |

---

## 🚀 Usage

### Option A: Launch Web Dashboard (Recommended)
```bash
python3 dashboard.py
# Or use the launcher script:
./start.sh
```
Open **`http://localhost:5050`** in your browser to view accounts, run harvests, and sync to 9Router.

### Option B: CLI Direct Execution

**Harvest Dahl Inference Accounts:**
```bash
python3 dahl-api-harvester/register_dahl.py --count 5
```

**Harvest OpenRouter Accounts:**
```bash
python3 openrouter-api-harvester/register_openrouter.py --count 5
```

**Harvest Grok xAI CLI Tokens:**
```bash
python3 grok-token-harvester/register_grok_tokens.py --count 5
```

**Harvest TokenHarbor.ai Accounts:**
```bash
python3 tokenharbor-api-harvester/register_tokenharbor.py --count 5
```

---

## 🔒 Security & Privacy Notice
All generated credentials (`*.txt`, `keys/`, `grok_accounts.json`, `.env`) are strictly excluded in `.gitignore` to prevent any sensitive data leakage.

---

## 📜 License
MIT License. For educational and research purposes only.
