import os, sys, json, time, re, threading, subprocess, requests
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH, override=True)
OPENROUTER_FILE = os.path.join(BASE_DIR, "openrouter-api-harvester", "keys", "openrouter_keys.txt")
GROK_FILE = os.path.join(BASE_DIR, "grok-token-harvester", "grok_accounts.json")
DAHL_FILE = os.path.join(BASE_DIR, "dahl-api-harvester", "keys", "dahl_keys.txt")

# Farming task tracker
farm_state = {
    "running": False,
    "provider": None,
    "count": 0,
    "log": ""
}

# 9Router Bridge Configuration (Loaded securely from .env)
ROUTER_BASE_URL = (os.getenv("ROUTER_BASE_URL") or os.getenv("NINEROUTER_URL") or "https://api.thirx.com").rstrip("/")
ROUTER_PASSWORD = os.getenv("ROUTER_PASSWORD") or os.getenv("NINEROUTER_PASSWORD") or ""
router_session = None
router_session_lock = threading.Lock()

def get_router_session():
    global router_session
    with router_session_lock:
        if router_session is None:
            router_session = requests.Session()
            try:
                r = router_session.post(f"{ROUTER_BASE_URL}/api/auth/login", json={"password": ROUTER_PASSWORD}, timeout=8)
                if r.status_code != 200:
                    router_session = None
            except Exception:
                router_session = None
        return router_session

def fetch_9router_connections():
    s = get_router_session()
    if not s:
        return []
    try:
        r = s.get(f"{ROUTER_BASE_URL}/api/providers", timeout=8)
        if r.status_code == 401:
            global router_session
            router_session = None
            s = get_router_session()
            if s:
                r = s.get(f"{ROUTER_BASE_URL}/api/providers", timeout=8)
        if r.status_code == 200:
            return r.json().get("connections", [])
    except Exception as e:
        print(f"[9Router] Error fetching connections: {e}")
    return []

def delete_9router_connection(connection_id):
    if not connection_id:
        return False, "No connection ID"
    s = get_router_session()
    if not s:
        return False, "Cannot connect to 9Router"
    try:
        r = s.delete(f"{ROUTER_BASE_URL}/api/providers/{connection_id}", timeout=8)
        if r.status_code in (200, 204):
            return True, "Deleted from 9Router"
        elif r.status_code == 404:
            return True, "Connection already removed from 9Router"
        elif r.status_code == 401:
            global router_session
            router_session = None
            s = get_router_session()
            if s:
                r = s.delete(f"{ROUTER_BASE_URL}/api/providers/{connection_id}", timeout=8)
                if r.status_code in (200, 204, 404):
                    return True, "Deleted from 9Router"
        return False, f"HTTP {r.status_code}: {r.text[:80]}"
    except Exception as e:
        return False, str(e)

def match_router_connection(prov, item, conns):
    for c in conns:
        cp = (c.get("provider") or "").lower()
        cn = (c.get("name") or "").lower()
        ce = (c.get("email") or "").lower()
        cs = c.get("providerSpecificData") or {}

        if prov == "openrouter" and "openrouter" in cp:
            em = item.get("email", "").lower()
            if em and (em in cn or em == ce):
                return c.get("id")
        elif prov == "grok" and "grok" in cp:
            em = item.get("email", "").lower()
            if em and (em in cn or em == ce or em in cs.get("idToken", "")):
                return c.get("id")
        elif prov == "dahl" and "dahl" in cp:
            un = item.get("username", "").lower()
            if un and (un in cn or cn in un):
                return c.get("id")
            if cn == "k" and un == "user_53515":
                return c.get("id")
    return None

def push_item_to_9router(prov, item, session):
    if prov == "openrouter":
        payload = {"provider": "openrouter", "apiKey": item["key"], "name": f"{item['email']} 1"}
        r = session.post(f"{ROUTER_BASE_URL}/api/providers", json=payload, timeout=10)
    elif prov == "dahl":
        payload = {"provider": "dahl", "apiKey": item["key"], "name": f"dahl_{item.get('username')}"}
        r = session.post(f"{ROUTER_BASE_URL}/api/providers", json=payload, timeout=10)
    elif prov == "grok":
        clean_item = {
            "access_token": item.get("access_token"),
            "refresh_token": item.get("refresh_token"),
            "id_token": item.get("id_token"),
            "email": item.get("email")
        }
        r = session.post(f"{ROUTER_BASE_URL}/api/oauth/grok-cli/bulk-import", json=[clean_item], timeout=12)
        if r.status_code == 200:
            res_data = r.json()
            if res_data.get("success", 0) > 0:
                return True, "Synced successfully"
            else:
                err = res_data.get("results", [{}])[0].get("error", "Import failed")
                return False, err
        else:
            return False, f"HTTP {r.status_code}"
    else:
        return False, f"Provider {prov} does not support direct sync"

    if r.status_code in (200, 201):
        return True, "Synced successfully"
    else:
        try:
            err = r.json().get("error", f"HTTP {r.status_code}")
        except Exception:
            err = f"HTTP {r.status_code}"
        return False, err

def sync_single_to_9router(prov, item_id):
    conns = fetch_9router_connections()
    item = None
    if prov == "openrouter":
        item = next((k for k in read_openrouter_keys() if k["id"] == item_id), None)
    elif prov == "dahl":
        item = next((k for k in read_dahl_keys() if k["id"] == item_id), None)
    elif prov == "grok":
        item = next((k for k in read_grok_accounts() if k["id"] == item_id), None)

    if not item:
        return False, "Item not found"

    # Deduplication check: if already in 9Router, do not push duplicate!
    if match_router_connection(prov, item, conns):
        return True, "Already in 9Router (Skipped)"

    s = get_router_session()
    if not s:
        return False, "Cannot connect to 9Router"

    return push_item_to_9router(prov, item, s)

def sync_all_to_9router(target_prov="all"):
    conns = fetch_9router_connections()
    tasks = []

    if target_prov in ("all", "openrouter"):
        for k in read_openrouter_keys():
            tasks.append(("openrouter", k))
    if target_prov in ("all", "dahl"):
        for k in read_dahl_keys():
            tasks.append(("dahl", k))
    if target_prov in ("all", "grok"):
        for k in read_grok_accounts():
            tasks.append(("grok", k))

    s = get_router_session()
    if not s:
        return False, 0, 0, ["Cannot connect to 9Router"]

    synced = 0
    skipped = 0
    errors = []

    for prov, item in tasks:
        # Deduplication check: if already in 9Router, SKIP completely!
        if match_router_connection(prov, item, conns):
            skipped += 1
            continue

        ok, msg = push_item_to_9router(prov, item, s)
        if ok:
            synced += 1
            conns = fetch_9router_connections()
        else:
            ident = item.get("email") or item.get("username")
            errors.append(f"{prov} ({ident}): {msg}")

    return True, synced, skipped, errors

def read_openrouter_keys():
    keys = []
    if os.path.exists(OPENROUTER_FILE):
        with open(OPENROUTER_FILE, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "|" in line:
                    email, key = line.split("|", 1)
                else:
                    email, key = f"openrouter_key_{idx+1}", line
                keys.append({"id": f"openrouter_{idx}", "email": email.strip(), "key": key.strip()})
    return keys

def save_openrouter_keys(keys):
    os.makedirs(os.path.dirname(OPENROUTER_FILE), exist_ok=True)
    with open(OPENROUTER_FILE, "w", encoding="utf-8") as f:
        for k in keys:
            f.write(f"{k['email']}|{k['key']}\n")

def read_grok_accounts():
    if os.path.exists(GROK_FILE):
        try:
            with open(GROK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for idx, acc in enumerate(data):
                        acc["id"] = f"grok_{idx}"
                    return data
        except Exception:
            return []
    return []

def save_grok_accounts(accounts):
    clean_accs = []
    for a in accounts:
        clean = {k: v for k, v in a.items() if k not in ["id", "status", "latency", "details", "router_id", "in_router"]}
        clean_accs.append(clean)
    os.makedirs(os.path.dirname(GROK_FILE), exist_ok=True)
    with open(GROK_FILE, "w", encoding="utf-8") as f:
        json.dump(clean_accs, f, indent=2)

def read_dahl_keys():
    keys = []
    if os.path.exists(DAHL_FILE):
        with open(DAHL_FILE, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "|" in line:
                    username, key = line.split("|", 1)
                else:
                    username, key = f"dahl_{idx+1}", line
                keys.append({"id": f"dahl_{idx}", "username": username.strip(), "key": key.strip()})
    return keys

def save_dahl_keys(keys):
    os.makedirs(os.path.dirname(DAHL_FILE), exist_ok=True)
    with open(DAHL_FILE, "w", encoding="utf-8") as f:
        for k in keys:
            f.write(f"{k['username']}|{k['key']}\n")

def test_single_openrouter(key):
    headers = {
        "Authorization": f"Bearer {key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "Dashboard Validator",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    t0 = time.time()
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=12)
        elapsed = time.time() - t0
        if r.status_code == 200:
            routed = r.json().get("model", "free")
            return {"active": True, "latency": round(elapsed, 2), "routed": routed, "error": None}
        return {"active": False, "latency": round(elapsed, 2), "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"active": False, "latency": None, "error": str(e)[:50]}

def test_single_grok(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "User-Agent": "grok-pager/1.0.44 grok-shell/1.0.44 (linux; x86_64)",
        "x-xai-token-auth": "xai-grok-cli",
        "x-grok-client-version": "1.0.44"
    }
    t0 = time.time()
    try:
        r = requests.get("https://cli-chat-proxy.grok.com/v1/user", headers=headers, timeout=10)
        elapsed = time.time() - t0
        if r.status_code == 200:
            data = r.json()
            return {
                "active": True,
                "latency": round(elapsed, 2),
                "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
                "grokCode": data.get("hasGrokCodeAccess", False),
                "error": None
            }

        # Auto-refresh if access token expired (6h lifecycle)
        if r.status_code == 401:
            accs = read_grok_accounts()
            target_acc = next((a for a in accs if a.get("access_token") == access_token), None)
            if target_acc and target_acc.get("refresh_token"):
                ref_res = requests.post("https://auth.x.ai/oauth2/token", data={
                    "grant_type": "refresh_token",
                    "refresh_token": target_acc["refresh_token"],
                    "client_id": "b1a00492-073a-47ea-816f-4c329264a828"
                }, headers={"User-Agent": headers["User-Agent"]}, timeout=10)
                if ref_res.status_code == 200:
                    ref_data = ref_res.json()
                    target_acc["access_token"] = ref_data.get("access_token")
                    if ref_data.get("refresh_token"):
                        target_acc["refresh_token"] = ref_data.get("refresh_token")
                    save_grok_accounts(accs)
                    headers["Authorization"] = f"Bearer {target_acc['access_token']}"
                    r2 = requests.get("https://cli-chat-proxy.grok.com/v1/user", headers=headers, timeout=10)
                    if r2.status_code == 200:
                        data = r2.json()
                        return {
                            "active": True,
                            "latency": round(time.time() - t0, 2),
                            "name": f"{data.get('firstName', '')} {data.get('lastName', '')}".strip(),
                            "grokCode": data.get("hasGrokCodeAccess", False),
                            "error": None
                        }

        return {"active": False, "latency": round(elapsed, 2), "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"active": False, "latency": None, "error": str(e)[:50]}

def test_single_dahl(key):
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    payload = {
        "model": "deepseek-ai/DeepSeek-V4-Flash-0731",
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 5
    }
    t0 = time.time()
    try:
        r = requests.post("https://inference.dahl.global/v1/chat/completions", headers=headers, json=payload, timeout=12)
        elapsed = time.time() - t0
        if r.status_code == 200:
            return {"active": True, "latency": round(elapsed, 2), "model": "DeepSeek-V4", "error": None}
        return {"active": False, "latency": round(elapsed, 2), "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"active": False, "latency": None, "error": str(e)[:50]}

def run_farm_task(provider, count):
    global farm_state
    farm_state["running"] = True
    farm_state["provider"] = provider
    farm_state["count"] = count
    farm_state["log"] = f"Started harvest for {provider} (count={count})...\n"

    try:
        if provider == "openrouter":
            cwd = os.path.join(BASE_DIR, "openrouter-api-harvester")
            script = "register_openrouter.py"
        elif provider == "grok":
            cwd = os.path.join(BASE_DIR, "grok-token-harvester")
            script = "register_grok_tokens.py"
        elif provider == "dahl":
            cwd = os.path.join(BASE_DIR, "dahl-api-harvester")
            script = "register_dahl.py"
        else:
            return

        try:
            subprocess.run(["xhost", "+local:"], capture_output=True, timeout=2)
        except Exception:
            pass

        cmd = [sys.executable, "-u", script, "--count", str(count)]
        child_env = os.environ.copy()
        if not child_env.get("DISPLAY"):
            child_env["DISPLAY"] = ":0.0"
        if not child_env.get("XAUTHORITY") and os.path.exists("/home/film/.Xauthority"):
            child_env["XAUTHORITY"] = "/home/film/.Xauthority"
        proc = subprocess.Popen(cmd, cwd=cwd, env=child_env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in proc.stdout:
            farm_state["log"] += line
        proc.wait()
        farm_state["log"] += f"\n[Completed with code {proc.returncode}]"
    except Exception as e:
        farm_state["log"] += f"\nError: {e}"
    finally:
        farm_state["running"] = False

HTML_PAGE = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Harvester Suite - Management Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          fontFamily: {
            sans: ['Inter', 'sans-serif'],
            mono: ['JetBrains Mono', 'monospace'],
          }
        }
      }
    }
  </script>
  <style>
    body {
      background-color: #080C14;
      color: #E2E8F0;
    }
    .glass-panel {
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(51, 65, 85, 0.45);
    }
    .stat-card {
      transition: all 0.2s ease-in-out;
    }
    .stat-card:hover {
      transform: translateY(-2px);
      border-color: rgba(99, 102, 241, 0.5);
    }
    .tab-btn.active {
      background-color: rgba(30, 41, 59, 0.9);
      border-color: rgba(99, 102, 241, 0.6);
      color: #FFFFFF;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
    }
    .table-row-hover:hover {
      background-color: rgba(30, 41, 59, 0.35);
    }
  </style>
</head>
<body class="min-h-screen font-sans flex flex-col antialiased selection:bg-indigo-500 selection:text-white">

  <!-- Header -->
  <header class="border-b border-slate-800/80 bg-slate-900/70 backdrop-blur sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
          <i class="fa-solid fa-server text-sm"></i>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-sm font-semibold tracking-tight text-white">AI Harvester Suite</h1>
            <span id="routerStatusBadge" class="text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1.5"><i class="fa-solid fa-circle-notch fa-spin text-[8px]"></i> <span>Connecting 9Router...</span></span>
          </div>
          <p class="text-[11px] text-slate-400">Automated Multi-Provider Credential & Quota Manager</p>
        </div>
      </div>
      
      <div class="flex items-center gap-2">
        <button onclick="refreshAllData()" id="refreshBtn" class="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800/80 hover:bg-slate-700 text-xs font-medium text-slate-200 transition flex items-center gap-1.5 shadow-sm">
          <i class="fa-solid fa-rotate text-xs"></i>
          <span>Reload</span>
        </button>
        <button onclick="testAllKeys()" id="testAllBtn" class="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-xs font-medium text-white transition flex items-center gap-1.5 shadow-md shadow-indigo-600/20">
          <i class="fa-solid fa-vial-circle-check text-xs"></i>
          <span>Check All</span>
        </button>
        <button onclick="syncAllToRouter('all')" id="syncAllBtn" class="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-xs font-medium text-white transition flex items-center gap-1.5 shadow-md shadow-emerald-600/20" title="Push all unsynced accounts to 9Router (already synced accounts are skipped)">
          <i class="fa-solid fa-cloud-arrow-up text-xs"></i>
          <span>Sync All to 9R</span>
        </button>
      </div>
    </div>
  </header>

  <!-- Farming Status Banner -->
  <div id="farmBanner" class="hidden border-b border-amber-500/30 bg-amber-500/10 px-4 py-2">
    <div class="max-w-7xl mx-auto flex items-center justify-between text-xs text-amber-300">
      <div class="flex items-center gap-2">
        <i class="fa-solid fa-circle-notch fa-spin text-amber-400"></i>
        <span id="farmBannerText">Harvesting in progress...</span>
      </div>
      <button onclick="openLogModal()" class="underline hover:text-white transition font-medium">View Live Log</button>
    </div>
  </div>

  <!-- Main Container -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

    <!-- Top Stats (Clickable to switch tab) -->
    <div class="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
      
      <!-- Dahl Stat -->
      <div onclick="switchTab('dahl')" class="stat-card glass-panel rounded-xl p-3.5 cursor-pointer border border-slate-800 flex items-center justify-between">
        <div>
          <span class="text-[11px] font-medium uppercase tracking-wider text-slate-400">Dahl API</span>
          <div class="text-xl font-bold text-white mt-0.5 flex items-baseline gap-1.5">
            <span id="dahlCount">0</span>
            <span class="text-[10px] font-normal text-slate-400">keys</span>
          </div>
        </div>
        <div class="w-9 h-9 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
          <i class="fa-solid fa-cube text-sm"></i>
        </div>
      </div>

      <!-- OpenRouter Stat -->
      <div onclick="switchTab('openrouter')" class="stat-card glass-panel rounded-xl p-3.5 cursor-pointer border border-slate-800 flex items-center justify-between">
        <div>
          <span class="text-[11px] font-medium uppercase tracking-wider text-slate-400">OpenRouter</span>
          <div class="text-xl font-bold text-white mt-0.5 flex items-baseline gap-1.5">
            <span id="openrouterCount">0</span>
            <span class="text-[10px] font-normal text-slate-400">keys</span>
          </div>
        </div>
        <div class="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400">
          <i class="fa-solid fa-network-wired text-sm"></i>
        </div>
      </div>

      <!-- Grok CLI Stat -->
      <div onclick="switchTab('grok')" class="stat-card glass-panel rounded-xl p-3.5 cursor-pointer border border-slate-800 flex items-center justify-between">
        <div>
          <span class="text-[11px] font-medium uppercase tracking-wider text-slate-400">Grok CLI</span>
          <div class="text-xl font-bold text-white mt-0.5 flex items-baseline gap-1.5">
            <span id="grokCount">0</span>
            <span class="text-[10px] font-normal text-slate-400">accs</span>
          </div>
        </div>
        <div class="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-sky-400">
          <i class="fa-solid fa-terminal text-sm"></i>
        </div>
      </div>

    </div>

    <!-- Navigation Tabs Bar -->
    <div class="flex items-center justify-between border-b border-slate-800 pb-2">
      <div class="flex items-center gap-1.5 overflow-x-auto py-1 text-xs">
        <button onclick="switchTab('all')" id="tabBtn_all" class="tab-btn px-3 py-1.5 rounded-lg border border-transparent font-medium text-slate-400 hover:text-white transition flex items-center gap-1.5">
          <i class="fa-solid fa-layer-group text-slate-400"></i>
          <span>All Providers</span>
          <span id="badge_all" class="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-400">0</span>
        </button>
        <button onclick="switchTab('dahl')" id="tabBtn_dahl" class="tab-btn px-3 py-1.5 rounded-lg border border-transparent font-medium text-slate-400 hover:text-white transition flex items-center gap-1.5">
          <i class="fa-solid fa-cube text-rose-400"></i>
          <span>Dahl</span>
          <span id="badge_dahl" class="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-400">0</span>
        </button>
        <button onclick="switchTab('openrouter')" id="tabBtn_openrouter" class="tab-btn px-3 py-1.5 rounded-lg border border-transparent font-medium text-slate-400 hover:text-white transition flex items-center gap-1.5">
          <i class="fa-solid fa-network-wired text-indigo-400"></i>
          <span>OpenRouter</span>
          <span id="badge_openrouter" class="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-400">0</span>
        </button>
        <button onclick="switchTab('grok')" id="tabBtn_grok" class="tab-btn px-3 py-1.5 rounded-lg border border-transparent font-medium text-slate-400 hover:text-white transition flex items-center gap-1.5">
          <i class="fa-solid fa-terminal text-sky-400"></i>
          <span>Grok CLI</span>
          <span id="badge_grok" class="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] text-slate-400">0</span>
        </button>
      </div>

      <!-- Quick Search input -->
      <div class="relative hidden md:block w-64">
        <i class="fa-solid fa-magnifying-glass absolute left-3 top-2.5 text-xs text-slate-500"></i>
        <input type="text" id="searchFilter" oninput="handleSearch(this.value)" placeholder="Filter credentials..." class="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition">
      </div>
    </div>

    <!-- ==================== TAB PANELS ==================== -->

    <!-- PANEL 0: ALL CREDENTIALS (UNIFIED VIEW) -->
    <div id="panel_all" class="tab-panel space-y-4">
      <div class="glass-panel rounded-xl overflow-hidden border border-slate-800">
        <div class="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div>
            <h2 class="text-sm font-semibold text-white">All Active Credentials</h2>
            <p class="text-xs text-slate-400">Unified list of all AI accounts with real-time 9Router sync status</p>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-slate-400">Total: <strong id="totalAllCount" class="text-white">0</strong> accounts</span>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400 bg-slate-950/40 uppercase tracking-wider text-[10px]">
                <th class="py-3 px-4">Provider</th>
                <th class="py-3 px-4">Account / Identifier</th>
                <th class="py-3 px-4">Credential Preview</th>
                <th class="py-3 px-4">9Router Sync</th>
                <th class="py-3 px-4">Status / Health</th>
                <th class="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="allTbody" class="divide-y divide-slate-800/60 font-mono">
              <tr><td colspan="6" class="text-center py-8 text-slate-500">Loading all credentials...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>


    <!-- PANEL 2: OPENROUTER -->
    <div id="panel_openrouter" class="tab-panel hidden space-y-4">
      <div class="glass-panel rounded-xl overflow-hidden border border-slate-800">
        <div class="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
              <i class="fa-solid fa-network-wired text-sm"></i>
            </div>
            <div>
              <h2 class="text-sm font-semibold text-white">OpenRouter API Harvester</h2>
              <p class="text-xs text-slate-400">Aggregated gateway for 20+ free open-weight models</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="testKeys('openrouter')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-vial-circle-check text-xs text-indigo-400"></i>
              <span>Check OpenRouter</span>
            </button>
            <button onclick="syncAllToRouter('openrouter')" class="px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30 text-xs transition flex items-center gap-1.5 shadow-sm" title="Sync all OpenRouter keys to 9Router">
              <i class="fa-solid fa-cloud-arrow-up text-xs"></i>
              <span>Sync to 9Router</span>
            </button>
            <button onclick="copyAllOpenRouter()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-copy text-xs"></i>
              <span>Copy All (9Router Format)</span>
            </button>
            <div class="inline-flex rounded-lg border border-slate-700 bg-slate-900/90 p-0.5 shadow-sm">
              <button onclick="triggerFarm('openrouter', 1)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 1 account">+1</button>
              <button onclick="triggerFarm('openrouter', 5)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 5 accounts with rotating proxies">+5</button>
              <button onclick="triggerFarm('openrouter', 10)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 10 accounts with rotating proxies">+10</button>
              <button onclick="promptFarm('openrouter')" class="px-2.5 py-1 rounded text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1 shadow-sm" title="Farm custom quantity">
                <i class="fa-solid fa-play text-[9px]"></i>
                <span>Farm</span>
              </button>
            </div>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400 bg-slate-950/40 uppercase tracking-wider text-[10px]">
                <th class="py-3 px-4">Account Email</th>
                <th class="py-3 px-4">API Key (sk-or-v1-...)</th>
                <th class="py-3 px-4">9Router Sync</th>
                <th class="py-3 px-4">Health & Latency</th>
                <th class="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="openrouterTbody" class="divide-y divide-slate-800/60 font-mono">
              <tr><td colspan="5" class="text-center py-8 text-slate-500">Loading keys...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- PANEL 2: GROK CLI -->
    <div id="panel_grok" class="tab-panel hidden space-y-4">
      <div class="glass-panel rounded-xl overflow-hidden border border-slate-800">
        <div class="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
              <i class="fa-solid fa-terminal text-sm"></i>
            </div>
            <div>
              <h2 class="text-sm font-semibold text-white">xAI Grok CLI Harvester</h2>
              <p class="text-xs text-slate-400">OAuth2 Device Code Flow with auto-refreshing offline tokens</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="testKeys('grok')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-vial-circle-check text-xs text-sky-400"></i>
              <span>Check Grok</span>
            </button>
            <button onclick="syncAllToRouter('grok')" class="px-3 py-1.5 rounded-lg bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 text-xs transition flex items-center gap-1.5 shadow-sm" title="Sync all Grok accounts to 9Router">
              <i class="fa-solid fa-cloud-arrow-up text-xs"></i>
              <span>Sync to 9Router</span>
            </button>
            <button onclick="copyAllGrok()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-file-export text-xs"></i>
              <span>Export Batch JSON (9Router)</span>
            </button>
            <div class="inline-flex rounded-lg border border-slate-700 bg-slate-900/90 p-0.5 shadow-sm">
              <button onclick="triggerFarm('grok', 1)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 1 account">+1</button>
              <button onclick="triggerFarm('grok', 5)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 5 accounts with rotating proxies">+5</button>
              <button onclick="triggerFarm('grok', 10)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 10 accounts with rotating proxies">+10</button>
              <button onclick="promptFarm('grok')" class="px-2.5 py-1 rounded text-xs font-medium bg-sky-600 hover:bg-sky-500 text-white transition flex items-center gap-1 shadow-sm" title="Farm custom quantity">
                <i class="fa-solid fa-play text-[9px]"></i>
                <span>Farm</span>
              </button>
            </div>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400 bg-slate-950/40 uppercase tracking-wider text-[10px]">
                <th class="py-3 px-4">Account Email</th>
                <th class="py-3 px-4">OAuth Access Token</th>
                <th class="py-3 px-4">Identity & GrokCode</th>
                <th class="py-3 px-4">9Router Sync</th>
                <th class="py-3 px-4">Health & Latency</th>
                <th class="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="grokTbody" class="divide-y divide-slate-800/60 font-mono">
              <tr><td colspan="6" class="text-center py-8 text-slate-500">Loading accounts...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>


    <!-- PANEL 3: DAHL -->
    <div id="panel_dahl" class="tab-panel hidden space-y-4">
      <div class="glass-panel rounded-xl overflow-hidden border border-slate-800">
        <div class="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400">
              <i class="fa-solid fa-cube text-sm"></i>
            </div>
            <div>
              <h2 class="text-sm font-semibold text-white">Dahl Inference Harvester</h2>
              <p class="text-xs text-slate-400">High-speed inference on DeepSeek-V4 Flash & GLM-5.3</p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="testKeys('dahl')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-vial-circle-check text-xs text-rose-400"></i>
              <span>Check Dahl</span>
            </button>
            <button onclick="syncAllToRouter('dahl')" class="px-3 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 text-xs transition flex items-center gap-1.5 shadow-sm" title="Sync all Dahl keys to 9Router">
              <i class="fa-solid fa-cloud-arrow-up text-xs"></i>
              <span>Sync to 9Router</span>
            </button>
            <button onclick="copyAllDahl()" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-copy text-xs"></i>
              <span>Copy All (9Router Format)</span>
            </button>
            <div class="inline-flex rounded-lg border border-slate-700 bg-slate-900/90 p-0.5 shadow-sm">
              <button onclick="triggerFarm('dahl', 1)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 1 account">+1</button>
              <button onclick="triggerFarm('dahl', 5)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 5 accounts with rotating proxies">+5</button>
              <button onclick="triggerFarm('dahl', 10)" class="px-2.5 py-1 rounded text-xs font-medium text-slate-300 hover:text-white hover:bg-slate-800 transition" title="Farm 10 accounts with rotating proxies">+10</button>
              <button onclick="promptFarm('dahl')" class="px-2.5 py-1 rounded text-xs font-medium bg-rose-600 hover:bg-rose-500 text-white transition flex items-center gap-1 shadow-sm" title="Farm custom quantity">
                <i class="fa-solid fa-play text-[9px]"></i>
                <span>Farm</span>
              </button>
            </div>
          </div>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400 bg-slate-950/40 uppercase tracking-wider text-[10px]">
                <th class="py-3 px-4">Account Username</th>
                <th class="py-3 px-4">API Key (dahl_...)</th>
                <th class="py-3 px-4">9Router Sync</th>
                <th class="py-3 px-4">Health & Latency</th>
                <th class="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody id="dahlTbody" class="divide-y divide-slate-800/60 font-mono">
              <tr><td colspan="5" class="text-center py-8 text-slate-500">Loading keys...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </main>

  <!-- Log Modal -->
  <div id="logModal" class="hidden fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="glass-panel rounded-2xl max-w-2xl w-full flex flex-col overflow-hidden shadow-2xl border border-slate-700">
      <div class="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
        <div class="flex items-center gap-2.5 text-sm font-semibold text-white">
          <i class="fa-solid fa-terminal text-emerald-400"></i>
          <span>Live Harvest Log</span>
        </div>
        <button onclick="closeLogModal()" class="text-slate-400 hover:text-white p-1">
          <i class="fa-solid fa-xmark text-sm"></i>
        </button>
      </div>
      <div class="p-4 bg-black/70 font-mono text-xs text-emerald-400 h-80 overflow-y-auto whitespace-pre-wrap leading-relaxed" id="logContent">
        Connecting...
      </div>
    </div>
  </div>

  <!-- Toast Notification -->
  <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-12 opacity-0 transition duration-200 pointer-events-none px-4 py-2.5 rounded-lg bg-slate-800 border border-slate-700 text-xs font-medium text-white shadow-xl flex items-center gap-2">
    <i class="fa-solid fa-circle-check text-emerald-400" id="toastIcon"></i>
    <span id="toastMsg">Action completed</span>
  </div>

  <script>
    let appData = { dahl: [], openrouter: [], grok: [] };
    /* __INIT_DATA__ */
    let currentTab = 'all';
    let searchQuery = '';
    let testCache = {};

    function showToast(msg, isSuccess = true) {
      const toast = document.getElementById('toast');
      const toastMsg = document.getElementById('toastMsg');
      const toastIcon = document.getElementById('toastIcon');
      toastMsg.innerText = msg;
      toastIcon.className = isSuccess ? 'fa-solid fa-circle-check text-emerald-400' : 'fa-solid fa-circle-xmark text-rose-400';
      toast.classList.remove('translate-y-12', 'opacity-0');
      setTimeout(() => {
        toast.classList.add('translate-y-12', 'opacity-0');
      }, 2400);
    }

    async function copyToClipboard(text, btnElement, label = 'Copied') {
      try {
        await navigator.clipboard.writeText(text);
        if (btnElement) {
          const originalHTML = btnElement.innerHTML;
          btnElement.innerHTML = `<i class="fa-solid fa-check text-emerald-400"></i> ${label}`;
          setTimeout(() => { btnElement.innerHTML = originalHTML; }, 1800);
        }
        showToast('Copied to clipboard!');
      } catch (err) {
        showToast('Copy failed', false);
      }
    }

    function switchTab(tabId) {
      currentTab = tabId;
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      const activeBtn = document.getElementById(`tabBtn_${tabId}`);
      if (activeBtn) activeBtn.classList.add('active');

      document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.add('hidden'));
      const activePanel = document.getElementById(`panel_${tabId}`);
      if (activePanel) activePanel.classList.remove('hidden');
    }

    function handleSearch(val) {
      searchQuery = (val || '').toLowerCase().trim();
      renderAllViews();
    }

    function updateStatsAndRender() {
      const openrouterCount = appData.openrouter ? appData.openrouter.length : 0;
      const grokCount = appData.grok ? appData.grok.length : 0;
      const dahlCount = appData.dahl ? appData.dahl.length : 0;
      const totalCount = openrouterCount + grokCount + dahlCount;

      const oC = document.getElementById('openrouterCount'); if (oC) oC.innerText = openrouterCount;
      const grC = document.getElementById('grokCount'); if (grC) grC.innerText = grokCount;
      const dC = document.getElementById('dahlCount'); if (dC) dC.innerText = dahlCount;
      const tC = document.getElementById('totalAllCount'); if (tC) tC.innerText = totalCount;

      const bA = document.getElementById('badge_all'); if (bA) bA.innerText = totalCount;
      const bD = document.getElementById('badge_dahl'); if (bD) bD.innerText = dahlCount;
      const bO = document.getElementById('badge_openrouter'); if (bO) bO.innerText = openrouterCount;
      const bGr = document.getElementById('badge_grok'); if (bGr) bGr.innerText = grokCount;

      const routerBadge = document.getElementById('routerStatusBadge');
      if (routerBadge) {
        if (appData.router_connected) {
          routerBadge.className = 'text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 flex items-center gap-1.5';
          routerBadge.innerHTML = `<i class="fa-solid fa-circle text-[6px]"></i> <span>9Router Connected (${appData.router_count})</span>`;
        } else {
          routerBadge.className = 'text-[10px] font-mono uppercase px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700 flex items-center gap-1.5';
          routerBadge.innerHTML = `<i class="fa-regular fa-circle text-[6px]"></i> <span>9Router Offline</span>`;
        }
      }

      renderAllViews();
    }

    async function refreshAllData() {
      try {
        const res = await fetch('/api/data');
        appData = await res.json();
        updateStatsAndRender();
      } catch (err) {
        showToast('Failed to load credentials', false);
      }
    }

    function getStatusHTML(id) {
      const data = testCache[id];
      if (!data) return '<span class="text-slate-400">Unchecked</span>';
      if (data.loading) return '<span class="text-indigo-400 inline-flex items-center gap-1"><i class="fa-solid fa-circle-notch fa-spin text-xs"></i> Testing...</span>';
      if (data.active) {
        const detail = data.plan ? ` (${data.plan})` : (data.model ? ` (${data.model})` : '');
        return `<span class="text-emerald-400 inline-flex items-center gap-1 font-semibold" title="Valid${detail}"><i class="fa-solid fa-circle-check text-[10px]"></i> ${data.latency}s${detail}</span>`;
      }
      return `<span class="text-rose-400 inline-flex items-center gap-1" title="${data.error || 'Failed'}"><i class="fa-solid fa-circle-xmark text-[10px]"></i> Failed</span>`;
    }

    function updateStatusDisplay(id) {
      const html = getStatusHTML(id);
      document.querySelectorAll(`.status-cell-${id}`).forEach(el => {
        el.innerHTML = html;
      });
    }

    function renderRouterBadge(routerId) {
      if (routerId) {
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 text-[11px] font-sans font-medium" title="Synced in 9Router ID: ${routerId}"><i class="fa-solid fa-circle text-[6px]"></i> In 9Router</span>`;
      }
      return `<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/60 text-[11px] font-sans font-medium" title="Not synced to 9Router"><i class="fa-regular fa-circle text-[6px]"></i> Not Synced</span>`;
    }

    function renderSyncButton(provider, id, routerId) {
      if (routerId) {
        return `<button disabled class="px-2.5 py-1 rounded bg-slate-800/40 border border-slate-800 text-slate-500 text-[11px] cursor-not-allowed inline-flex items-center gap-1" title="Already connected to 9Router"><i class="fa-solid fa-check text-[10px] text-emerald-400"></i> Synced</button>`;
      }
      return `<button onclick="syncSingleKey('${provider}', '${id}', this)" class="px-2.5 py-1 rounded bg-indigo-600 hover:bg-indigo-500 text-white transition text-[11px] font-medium inline-flex items-center gap-1 shadow-sm shadow-indigo-600/20" title="Push this account to 9Router immediately"><i class="fa-solid fa-cloud-arrow-up text-[10px]"></i> Sync 9R</button>`;
    }

    function renderAllViews() {
      renderUnifiedAll();
      renderDahl();
      renderOpenRouter();
      renderGrok();
    }

    // 0. UNIFIED VIEW
    function renderUnifiedAll() {
      const el = document.getElementById('allTbody');
      const allRows = [];

      (appData.dahl || []).forEach(k => {
        if (!searchQuery || k.username.toLowerCase().includes(searchQuery) || k.key.toLowerCase().includes(searchQuery)) {
          allRows.push({
            rawProvider: 'dahl',
            id: k.id,
            router_id: k.router_id,
            provider: '<span class="px-2 py-0.5 rounded bg-rose-500/10 text-rose-400 border border-rose-500/30 text-[10px] font-semibold"><i class="fa-solid fa-cube mr-1"></i>Dahl</span>',
            identifier: k.username,
            credential: k.key,
            routerBadge: renderRouterBadge(k.router_id),
            statusId: `status_${k.id}`,
            testCall: `testKey('dahl', '${k.id}', '${k.key}')`,
            deleteCall: `deleteKey('dahl', '${k.id}', '${k.router_id || ''}')`
          });
        }
      });

      (appData.openrouter || []).forEach(k => {
        if (!searchQuery || k.email.toLowerCase().includes(searchQuery) || k.key.toLowerCase().includes(searchQuery)) {
          allRows.push({
            rawProvider: 'openrouter',
            id: k.id,
            router_id: k.router_id,
            provider: '<span class="px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30 text-[10px] font-semibold"><i class="fa-solid fa-network-wired mr-1"></i>OpenRouter</span>',
            identifier: k.email,
            credential: k.key,
            routerBadge: renderRouterBadge(k.router_id),
            statusId: `status_${k.id}`,
            testCall: `testKey('openrouter', '${k.id}', '${k.key}')`,
            deleteCall: `deleteKey('openrouter', '${k.id}', '${k.router_id || ''}')`
          });
        }
      });

      (appData.grok || []).forEach(a => {
        if (!searchQuery || a.email.toLowerCase().includes(searchQuery) || a.access_token.toLowerCase().includes(searchQuery)) {
          allRows.push({
            rawProvider: 'grok',
            id: a.id,
            router_id: a.router_id,
            provider: '<span class="px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30 text-[10px] font-semibold"><i class="fa-solid fa-terminal mr-1"></i>Grok CLI</span>',
            identifier: a.email,
            credential: a.access_token,
            routerBadge: renderRouterBadge(a.router_id),
            statusId: `status_${a.id}`,
            testCall: `testKey('grok', '${a.id}', '${a.access_token}')`,
            deleteCall: `deleteKey('grok', '${a.id}', '${a.router_id || ''}')`
          });
        }
      });

      if (allRows.length === 0) {
        el.innerHTML = '<tr><td colspan="6" class="text-center py-10 text-slate-500">No credentials found matching your filter</td></tr>';
        return;
      }

      el.innerHTML = allRows.map(row => `
        <tr class="table-row-hover transition-colors">
          <td class="py-3 px-4 whitespace-nowrap">${row.provider}</td>
          <td class="py-3 px-4 font-sans text-slate-200 font-medium">${row.identifier}</td>
          <td class="py-3 px-4">
            <span onclick="copyToClipboard('${row.credential}', null)" title="Click to copy full credential" class="cursor-pointer text-slate-400 hover:text-white bg-slate-900 px-2 py-1 rounded border border-slate-800 text-[11px] inline-flex items-center gap-1 transition">
              <span>${row.credential.substring(0, 16)}...${row.credential.substring(row.credential.length - 8)}</span>
              <i class="fa-solid fa-copy text-[10px] text-slate-500"></i>
            </span>
          </td>
          <td class="py-3 px-4 whitespace-nowrap">${row.routerBadge}</td>
          <td class="py-3 px-4 whitespace-nowrap">
            <div id="${row.statusId}" class="status-cell-${row.id} text-[11px]">${getStatusHTML(row.id)}</div>
          </td>
          <td class="py-3 px-4 text-right whitespace-nowrap space-x-2">
            <button onclick="${row.testCall}" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition text-[11px] inline-flex items-center gap-1">
              <i class="fa-solid fa-arrows-rotate text-[10px]"></i> Test
            </button>
            ${renderSyncButton(row.rawProvider, row.id, row.router_id)}
            <button onclick="${row.deleteCall}" title="Delete" class="p-1 text-rose-400 hover:text-rose-300 transition">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </td>
        </tr>
      `).join('');
    }
    function renderOpenRouter() {
      const el = document.getElementById('openrouterTbody');
      const items = (appData.openrouter || []).filter(k => !searchQuery || k.email.toLowerCase().includes(searchQuery) || k.key.toLowerCase().includes(searchQuery));
      if (items.length === 0) {
        el.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-slate-500">No OpenRouter keys found</td></tr>';
        return;
      }
      el.innerHTML = items.map(k => `
        <tr class="table-row-hover transition-colors">
          <td class="py-3 px-4 font-sans text-slate-200 font-medium">${k.email}</td>
          <td class="py-3 px-4">
            <span onclick="copyToClipboard('${k.key}', null)" title="Click to copy full key" class="cursor-pointer text-slate-400 hover:text-white bg-slate-900 px-2 py-1 rounded border border-slate-800 text-[11px] inline-flex items-center gap-1 transition">
              <span>${k.key.substring(0, 18)}...${k.key.substring(k.key.length - 8)}</span>
              <i class="fa-solid fa-copy text-[10px] text-slate-500"></i>
            </span>
          </td>
          <td class="py-3 px-4 whitespace-nowrap">${renderRouterBadge(k.router_id)}</td>
          <td class="py-3 px-4 whitespace-nowrap">
            <div id="status_${k.id}" class="status-cell-${k.id} text-[11px]">${getStatusHTML(k.id)}</div>
          </td>
          <td class="py-3 px-4 text-right whitespace-nowrap space-x-2">
            <button onclick="testKey('openrouter', '${k.id}', '${k.key}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition text-[11px] inline-flex items-center gap-1">
              <i class="fa-solid fa-arrows-rotate text-[10px]"></i> Test
            </button>
            ${renderSyncButton('openrouter', k.id, k.router_id)}
            <button onclick="deleteKey('openrouter', '${k.id}', '${k.router_id || ''}')" title="Delete key" class="p-1 text-rose-400 hover:text-rose-300 transition">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </td>
        </tr>
      `).join('');
    }

    // 3. GROK VIEW
    function renderGrok() {
      const el = document.getElementById('grokTbody');
      const items = (appData.grok || []).filter(a => !searchQuery || a.email.toLowerCase().includes(searchQuery) || a.access_token.toLowerCase().includes(searchQuery));
      if (items.length === 0) {
        el.innerHTML = '<tr><td colspan="6" class="text-center py-8 text-slate-500">No Grok accounts found</td></tr>';
        return;
      }
      el.innerHTML = items.map(a => `
        <tr class="table-row-hover transition-colors">
          <td class="py-3 px-4 font-sans text-slate-200 font-medium">${a.email}</td>
          <td class="py-3 px-4">
            <span onclick='copySingleGrok(${JSON.stringify(a)}, null)' title="Click to copy JSON" class="cursor-pointer text-slate-400 hover:text-white bg-slate-900 px-2 py-1 rounded border border-slate-800 text-[11px] inline-flex items-center gap-1 transition">
              <span>${a.access_token.substring(0, 16)}...</span>
              <i class="fa-solid fa-copy text-[10px] text-slate-500"></i>
            </span>
          </td>
          <td class="py-3 px-4 text-slate-300">
            <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-sky-500/10 text-sky-400 text-[11px] font-sans">
              <i class="fa-solid fa-user-check text-[10px]"></i> Verified Account
            </span>
          </td>
          <td class="py-3 px-4 whitespace-nowrap">${renderRouterBadge(a.router_id)}</td>
          <td class="py-3 px-4 whitespace-nowrap">
            <div id="status_${a.id}" class="status-cell-${a.id} text-[11px]">${getStatusHTML(a.id)}</div>
          </td>
          <td class="py-3 px-4 text-right whitespace-nowrap space-x-2">
            <button onclick="testKey('grok', '${a.id}', '${a.access_token}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition text-[11px] inline-flex items-center gap-1">
              <i class="fa-solid fa-arrows-rotate text-[10px]"></i> Test
            </button>
            ${renderSyncButton('grok', a.id, a.router_id)}
            <button onclick="deleteKey('grok', '${a.id}', '${a.router_id || ''}')" title="Delete account" class="p-1 text-rose-400 hover:text-rose-300 transition">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </td>
        </tr>
      `).join('');
    }


    // 3. DAHL VIEW
    function renderDahl() {
      const el = document.getElementById('dahlTbody');
      const items = (appData.dahl || []).filter(k => !searchQuery || k.username.toLowerCase().includes(searchQuery) || k.key.toLowerCase().includes(searchQuery));
      if (items.length === 0) {
        el.innerHTML = '<tr><td colspan="5" class="text-center py-8 text-slate-500">No Dahl keys found</td></tr>';
        return;
      }
      el.innerHTML = items.map(k => `
        <tr class="table-row-hover transition-colors">
          <td class="py-3 px-4 font-sans text-slate-200 font-medium">${k.username}</td>
          <td class="py-3 px-4">
            <span onclick="copyToClipboard('${k.key}', null)" title="Click to copy full key" class="cursor-pointer text-slate-400 hover:text-white bg-slate-900 px-2 py-1 rounded border border-slate-800 text-[11px] inline-flex items-center gap-1 transition">
              <span>${k.key.substring(0, 16)}...${k.key.substring(k.key.length - 8)}</span>
              <i class="fa-solid fa-copy text-[10px] text-slate-500"></i>
            </span>
          </td>
          <td class="py-3 px-4 whitespace-nowrap">${renderRouterBadge(k.router_id)}</td>
          <td class="py-3 px-4 whitespace-nowrap">
            <div id="status_${k.id}" class="status-cell-${k.id} text-[11px]">${getStatusHTML(k.id)}</div>
          </td>
          <td class="py-3 px-4 text-right whitespace-nowrap space-x-2">
            <button onclick="testKey('dahl', '${k.id}', '${k.key}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition text-[11px] inline-flex items-center gap-1">
              <i class="fa-solid fa-arrows-rotate text-[10px]"></i> Test
            </button>
            ${renderSyncButton('dahl', k.id, k.router_id)}
            <button onclick="deleteKey('dahl', '${k.id}', '${k.router_id || ''}')" title="Delete key" class="p-1 text-rose-400 hover:text-rose-300 transition">
              <i class="fa-solid fa-trash-can text-xs"></i>
            </button>
          </td>
        </tr>
      `).join('');
    }

    async function testKey(provider, id, secret) {
      testCache[id] = { loading: true };
      updateStatusDisplay(id);
      
      try {
        const res = await fetch('/api/test-single', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider, secret })
        });
        const data = await res.json();
        testCache[id] = data;
      } catch (err) {
        testCache[id] = { active: false, error: err.message };
      }
      updateStatusDisplay(id);
    }

    async function testKeys(targetProvider = 'all') {
      showToast(targetProvider === 'all' ? 'Testing all keys...' : `Testing all ${targetProvider} keys...`);
      if (targetProvider === 'all' || targetProvider === 'dahl') {
        for (const k of (appData.dahl || [])) { testKey('dahl', k.id, k.key); }
      }
      if (targetProvider === 'all' || targetProvider === 'openrouter') {
        for (const k of (appData.openrouter || [])) { testKey('openrouter', k.id, k.key); }
      }
      if (targetProvider === 'all' || targetProvider === 'grok') {
        for (const a of (appData.grok || [])) { testKey('grok', a.id, a.access_token); }
      }
    }

    function testAllKeys() {
      testKeys('all');
    }

    async function syncSingleKey(provider, id, btnEl) {
      if (btnEl) {
        btnEl.disabled = true;
        btnEl.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-[10px]"></i> Syncing...';
      }
      showToast('Pushing to 9Router...', true);
      try {
        const res = await fetch('/api/sync-single', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider, id })
        });
        const data = await res.json();
        if (res.ok && (data.success || data.status === 'ok')) {
          showToast(data.message || 'Synced to 9Router successfully!', true);
          await refreshAllData();
        } else {
          showToast(data.message || 'Failed to sync to 9Router', false);
          if (btnEl) {
            btnEl.disabled = false;
            btnEl.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-[10px]"></i> Sync 9R';
          }
        }
      } catch (err) {
        showToast('Network error: ' + err.message, false);
        if (btnEl) {
          btnEl.disabled = false;
          btnEl.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-[10px]"></i> Sync 9R';
        }
      }
    }

    async function syncAllToRouter(provider = 'all') {
      const btn = document.getElementById('syncAllBtn');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-xs"></i> Syncing...';
      }
      showToast('Syncing unsynced accounts to 9Router (skipping existing)...', true);
      try {
        const res = await fetch('/api/sync-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider })
        });
        const data = await res.json();
        if (res.ok && (data.success || data.status === 'ok')) {
          showToast(`Sync complete! Synced: ${data.synced}, Skipped: ${data.skipped}`, true);
          await refreshAllData();
        } else {
          showToast(data.message || 'Sync failed', false);
        }
      } catch (err) {
        showToast('Network error: ' + err.message, false);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = '<i class="fa-solid fa-cloud-arrow-up text-xs"></i> Sync All to 9R';
        }
      }
    }

    async function deleteKey(provider, id, routerId) {
      let deleteFromRouter = false;
      if (routerId) {
        const choice = confirm(
          `⚠️ บัญชีนี้กำลังเปิดใช้งานและเชื่อมต่ออยู่ใน 9Router!\\n\\n• กด [OK] เพื่อลบออกจากทั้ง Dashboard และ 9Router พร้อมกัน\\n• กด [Cancel] เพื่อยกเลิก (ไม่ลบข้อมูลใดๆ)`
        );
        if (!choice) return;
        deleteFromRouter = true;
      } else {
        if (!confirm('คุณต้องการลบข้อมูลนี้ออกจาก Dashboard ใช่หรือไม่?')) return;
      }

      try {
        const res = await fetch('/api/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider, id, delete_from_router: deleteFromRouter, router_id: routerId })
        });
        const data = await res.json();
        if (res.ok && data.success) {
          showToast(deleteFromRouter ? 'ลบออกจาก Dashboard และ 9Router สำเร็จ!' : 'Credential removed');
          refreshAllData();
        } else {
          showToast(data.error || 'Failed to delete', false);
        }
      } catch (e) {
        showToast('Network error on delete', false);
      }
    }


    function copyAllOpenRouter() {
      if (!appData.openrouter || appData.openrouter.length === 0) return showToast('No OpenRouter keys to copy', false);
      const text = appData.openrouter.map(k => `${k.email}|${k.key}`).join('\\n');
      copyToClipboard(text, null, 'Copied All');
    }

    function copySingleGrok(accountObj, btn) {
      const clean = {
        access_token: accountObj.access_token,
        refresh_token: accountObj.refresh_token,
        id_token: accountObj.id_token,
        email: accountObj.email
      };
      copyToClipboard(JSON.stringify([clean], null, 2), btn);
    }

    function copyAllGrok() {
      if (!appData.grok || appData.grok.length === 0) return showToast('No Grok accounts to copy', false);
      const cleanList = appData.grok.map(a => ({
        access_token: a.access_token,
        refresh_token: a.refresh_token,
        id_token: a.id_token,
        email: a.email
      }));
      copyToClipboard(JSON.stringify(cleanList, null, 2), null);
    }


    function copyAllDahl() {
      if (!appData.dahl || appData.dahl.length === 0) return showToast('No Dahl keys to copy', false);
      const text = appData.dahl.map(k => `${k.username}|${k.key}`).join('\\n');
      copyToClipboard(text, null, 'Copied All');
    }

    async function triggerFarm(provider, count) {
      const num = parseInt(count, 10) || 1;
      const res = await fetch('/api/farm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, count: num })
      });
      const data = await res.json();
      if (data.status === 'started') {
        showToast(`Harvest started for ${provider} (${num} accounts)`);
        checkFarmState();
      } else {
        showToast(data.message || 'Busy', false);
      }
    }

    function promptFarm(provider) {
      const input = prompt(`Enter number of accounts to farm for ${provider.toUpperCase()}:`, "5");
      if (input === null) return;
      const count = parseInt(input, 10);
      if (isNaN(count) || count < 1) {
        showToast("Please enter a valid number (>= 1)", false);
        return;
      }
      triggerFarm(provider, count);
    }

    let pollInterval = null;
    async function checkFarmState() {
      const res = await fetch('/api/farm-status');
      const state = await res.json();
      const banner = document.getElementById('farmBanner');
      const bannerText = document.getElementById('farmBannerText');
      const logContent = document.getElementById('logContent');

      if (logContent) {
        logContent.innerText = state.log || 'No active log';
        logContent.scrollTop = logContent.scrollHeight;
      }

      if (state.running) {
        banner.classList.remove('hidden');
        bannerText.innerText = `Harvesting in progress for ${state.provider} (target: ${state.count})...`;
        if (!pollInterval) {
          pollInterval = setInterval(checkFarmState, 1500);
        }
      } else {
        banner.classList.add('hidden');
        if (pollInterval) {
          clearInterval(pollInterval);
          pollInterval = null;
          refreshAllData();
          showToast('Harvest completed!');
        }
      }
    }

    function openLogModal() {
      document.getElementById('logModal').classList.remove('hidden');
    }

    function closeLogModal() {
      document.getElementById('logModal').classList.add('hidden');
    }

    // Initial Load
    switchTab('all');
    updateStatsAndRender();
    refreshAllData();
    setInterval(checkFarmState, 4000);
  </script>
</body>
</html>
"""

def get_all_dashboard_data():
    dahl_keys = read_dahl_keys()
    openrouter_keys = read_openrouter_keys()
    grok_accs = read_grok_accounts()

    conns = fetch_9router_connections()

    for k in dahl_keys:
        rid = match_router_connection("dahl", k, conns)
        k["router_id"] = rid
        k["in_router"] = bool(rid)

    for k in openrouter_keys:
        rid = match_router_connection("openrouter", k, conns)
        k["router_id"] = rid
        k["in_router"] = bool(rid)

    for a in grok_accs:
        rid = match_router_connection("grok", a, conns)
        a["router_id"] = rid
        a["in_router"] = bool(rid)

    return {
        "dahl": dahl_keys,
        "openrouter": openrouter_keys,
        "grok": grok_accs,
        "router_connected": len(conns) > 0,
        "router_count": len(conns)
    }

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            data = get_all_dashboard_data()
            page = HTML_PAGE.replace(
                "/* __INIT_DATA__ */",
                f"appData = {json.dumps(data)};"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page.encode("utf-8"))
        elif path == "/api/data":
            data = get_all_dashboard_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode("utf-8"))
        elif path == "/api/farm-status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(farm_state).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/test-single":
            provider = payload.get("provider")
            secret = payload.get("secret")
            if provider == "dahl":
                res = test_single_dahl(secret)
            elif provider == "openrouter":
                res = test_single_openrouter(secret)
            elif provider == "grok":
                res = test_single_grok(secret)
            else:
                res = {"active": False, "error": "Unknown provider"}
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/delete":
            provider = payload.get("provider")
            item_id = payload.get("id")
            delete_from_router = payload.get("delete_from_router", False)
            router_id = payload.get("router_id")

            router_deleted = False
            router_msg = ""
            if delete_from_router and router_id:
                success, router_msg = delete_9router_connection(router_id)
                router_deleted = success

            if provider == "dahl":
                keys = [k for k in read_dahl_keys() if k["id"] != item_id]
                save_dahl_keys(keys)
            elif provider == "openrouter":
                keys = [k for k in read_openrouter_keys() if k["id"] != item_id]
                save_openrouter_keys(keys)
            elif provider == "grok":
                accs = [a for a in read_grok_accounts() if a.get("id") != item_id]
                save_grok_accounts(accs)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": True, "router_deleted": router_deleted, "router_msg": router_msg}).encode("utf-8"))

        elif path == "/api/sync-single":
            provider = payload.get("provider")
            item_id = payload.get("id")
            ok, msg = sync_single_to_9router(provider, item_id)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "message": msg}).encode("utf-8"))

        elif path == "/api/sync-all":
            provider = payload.get("provider", "all")
            ok, synced, skipped, errors = sync_all_to_9router(provider)
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": ok, "synced": synced, "skipped": skipped, "errors": errors}).encode("utf-8"))

        elif path == "/api/farm":
            global farm_state
            if farm_state["running"]:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "busy", "message": "Another harvest is already running"}).encode("utf-8"))
            else:
                provider = payload.get("provider", "dahl")
                count = int(payload.get("count", 1))
                threading.Thread(target=run_farm_task, args=(provider, count), daemon=True).start()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "started"}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def main():
    port = 5050
    server = ThreadingHTTPServer(("0.0.0.0", port), DashboardHandler)
    print("=" * 65)
    print("   AI HARVESTER SUITE - WEB DASHBOARD (REVAMPED)")
    print(f"   Local URL   : http://localhost:{port}")
    print(f"   Network URL : http://0.0.0.0:{port}")
    print("=" * 65)
    print("Dashboard server running. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard server...")
        server.server_close()

if __name__ == "__main__":
    main()
