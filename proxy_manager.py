#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Proxy Manager: Automatic Rotating Proxy Provider for AI Account Harvesters
Supports Webshare.io API token integration with automatic local caching.
"""

import os
import time
import json
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_ENV = os.path.join(BASE_DIR, ".env")
if os.path.exists(PARENT_ENV):
    load_dotenv(PARENT_ENV, override=True)

CACHE_FILE = os.path.join(BASE_DIR, ".webshare_cache.json")

def get_webshare_proxies(api_key=None, force_refresh=False):
    """
    Fetch the list of direct proxies from Webshare.io.
    Caches the results locally for 2 hours to avoid rate limits.
    """
    key = api_key or os.getenv("WEBSHARE_API_KEY", "").strip()
    if not key:
        return []

    # Check local cache
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
                if cached.get("proxies") and (time.time() - cached.get("timestamp", 0) < 7200):
                    return cached["proxies"]
        except Exception:
            pass

    # Fetch from Webshare API
    try:
        url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct"
        headers = {"Authorization": f"Token {key}"}
        r = requests.get(url, headers=headers, timeout=12)
        if r.ok:
            results = r.json().get("results", [])
            proxies = []
            for p in results:
                username = p.get("username")
                password = p.get("password")
                address = p.get("proxy_address")
                port = p.get("port")
                country = p.get("country_code", "XX")
                proxy_str = f"http://{username}:{password}@{address}:{port}"
                proxies.append({
                    "url": proxy_str,
                    "ip": address,
                    "port": port,
                    "country": country
                })
            # Validate that proxies actually have active bandwidth / not 402
            if proxies:
                try:
                    test_p = proxies[0]["url"]
                    tr = requests.get("https://ipv4.icanhazip.com", proxies={"http": test_p, "https": test_p}, timeout=4)
                    if tr.status_code != 200:
                        print("[!] ⚠️ Webshare proxy returned non-200. Falling back to Direct IP.", flush=True)
                        return []
                except Exception:
                    print("[!] ⚠️ Webshare proxies currently unavailable or quota exhausted. Falling back to Direct IP.", flush=True)
                    return []

            # Save cache
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "proxies": proxies}, f, indent=2)
            return proxies
        else:
            print(f"[!] Webshare API error (HTTP {r.status_code}): {r.text[:100]}", flush=True)
    except Exception as e:
        print(f"[!] Failed to fetch Webshare proxies: {e}", flush=True)

    return []

def ensure_ip_authorized(api_key=None):
    """
    Ensures that the current public IP of this machine is authorized in Webshare.
    This allows Chromium/DrissionPage and headless browsers to connect directly
    without authentication prompts.
    """
    key = api_key or os.getenv("WEBSHARE_API_KEY", "").strip()
    if not key:
        return False
    try:
        my_ip = requests.get("https://ipv4.icanhazip.com", timeout=6).text.strip()
        headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
        r = requests.get("https://proxy.webshare.io/api/v2/proxy/ipauthorization/", headers=headers, timeout=8)
        if r.ok:
            items = r.json().get("results", [])
            auth_ips = [it.get("ip_address") for it in items]
            if my_ip in auth_ips:
                return True
            # Add IP
            post_r = requests.post("https://proxy.webshare.io/api/v2/proxy/ipauthorization/", headers=headers, json={"ip_address": my_ip}, timeout=8)
            if post_r.status_code in (200, 201):
                print(f"[*] 🌐 Webshare IP Authorization added for {my_ip}", flush=True)
                return True
    except Exception as e:
        print(f"[!] Warning: ensure_ip_authorized failed: {e}", flush=True)
    return False

def get_rotating_proxy(index=0):
    """
    Returns a proxy dict for the given index, or None if no proxies configured.
    """
    proxies = get_webshare_proxies()
    if not proxies:
        return None
    return proxies[index % len(proxies)]

if __name__ == "__main__":
    ensure_ip_authorized()
    proxies = get_webshare_proxies(force_refresh=True)
    print(f"Loaded {len(proxies)} proxies from Webshare:")
    for idx, p in enumerate(proxies):
        print(f"  [{idx+1}] {p['ip']}:{p['port']} ({p['country']})")
