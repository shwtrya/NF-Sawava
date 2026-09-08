import http.server
import json
import os
import random
import re
import socketserver
import threading
import time
import urllib.parse
from datetime import datetime
import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

PORT = 8080
PROXIES_FILE = "netflix_proxies.txt"

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

NETFLIX_COOKIE_NAMES = ("NetflixId", "SecureNetflixId", "NFTOKEN", "nfvdid", "OptanonConsent")
COUNTRY_CODE_NAMES = {
    'AR': 'Argentina', 'AU': 'Australia', 'BR': 'Brazil', 'CA': 'Canada',
    'DE': 'Germany', 'ES': 'Spain', 'FR': 'France', 'GB': 'United Kingdom',
    'ID': 'Indonesia', 'IN': 'India', 'IT': 'Italy', 'JP': 'Japan',
    'KR': 'South Korea', 'MY': 'Malaysia', 'MX': 'Mexico', 'NL': 'Netherlands',
    'PH': 'Philippines', 'SG': 'Singapore', 'TH': 'Thailand', 'TR': 'Turkey',
    'US': 'United States', 'VN': 'Vietnam',
}

def load_proxies():
    if not os.path.exists(PROXIES_FILE):
        return []
    with open(PROXIES_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]
    proxies = []
    for l in lines:
        parts = l.split(":")
        if len(parts) == 4:
            ip, port, u, p = parts
            proxies.append(f"http://{u}:{p}@{ip}:{port}")
        elif len(parts) == 2:
            ip, port = parts
            proxies.append(f"http://{ip}:{port}")
    return proxies

def get_proxy_dict(use_proxy):
    if not use_proxy:
        return None, "Direct"
    proxies = load_proxies()
    if not proxies:
        return None, "Direct (No Proxy File)"
    px = random.choice(proxies)
    clean = px.split("@")[-1] if "@" in px else px
    return {"http": px, "https": px}, f"Proxy ({clean})"

def extract_cookie_values(cookie_text):
    cookies = {}
    if not cookie_text:
        return cookies

    text = str(cookie_text).strip()

    # JSON export handling
    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        n = item.get("name")
                        v = item.get("value")
                        if n and v:
                            cookies[n] = urllib.parse.unquote(v) if "%" in v else v
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, str):
                        cookies[k] = urllib.parse.unquote(v) if "%" in v else v
        except Exception:
            pass

    # Netscape format
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies[parts[5]] = urllib.parse.unquote(parts[6]) if "%" in parts[6] else parts[6]

    # Header / Key=Value string parsing
    for part in re.split(r'[;\n\r]+', text):
        if "=" in part:
            k, v = part.split("=", 1)
            k = k.strip()
            v = v.strip().rstrip(".")
            if k in NETFLIX_COOKIE_NAMES and v:
                cookies[k] = urllib.parse.unquote(v) if "%" in v else v

    # Fallback regex search
    for name in NETFLIX_COOKIE_NAMES:
        if name not in cookies:
            m = re.search(rf'(?:^|[;\s|,{{])["\']?{re.escape(name)}["\']?\s*[:=]\s*["\']?([^"\'\s;,|}}]+)', text)
            if m:
                v = m.group(1).strip().rstrip(".")
                cookies[name] = urllib.parse.unquote(v) if "%" in v else v

    return cookies

def generate_nftoken(cookie_text, use_proxy=True):
    cookies = extract_cookie_values(cookie_text)
    nid = cookies.get("NetflixId")
    if not nid:
        raise ValueError("NetflixId cookie tidak ditemukan.")

    headers = dict(BASE_HEADERS)
    headers["Cookie"] = f"NetflixId={nid}"

    proxy_dict, route = get_proxy_dict(use_proxy)
    kw = {"proxies": proxy_dict} if proxy_dict else {}

    res = requests.get(API_URL, params=QUERY_PARAMS, headers=headers, timeout=25, verify=False, **kw)
    res.raise_for_status()

    data = res.json()
    token_node = (
        (((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default")
        or {}
    )
    token = token_node.get("token")
    expires = token_node.get("expires")
    if not token:
        raise ValueError("Netflix tidak mengembalikan NFToken (Cookie mungkin mati/expired).")

    exp_str = "Unknown"
    if isinstance(expires, (int, float)):
        ts = expires // 1000 if len(str(int(expires))) == 13 else expires
        exp_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

    return f"https://netflix.com/?nftoken={token}", exp_str, route

def normalize_country(code):
    if not code:
        return "Unknown"
    code = code.strip().upper()
    return f"{COUNTRY_CODE_NAMES.get(code, code)} ({code})" if code in COUNTRY_CODE_NAMES else code

def check_netflix_membership(cookie_text, use_proxy=True):
    cookies = extract_cookie_values(cookie_text)
    if "NetflixId" not in cookies:
        return {"live": False, "reason": "Cookie NetflixId tidak ditemukan."}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.netflix.com/browse',
    }

    proxy_dict, route = get_proxy_dict(use_proxy)
    kw = {"proxies": proxy_dict} if proxy_dict else {}

    session = requests.Session()
    try:
        # Pre-visit browse
        session.get('https://www.netflix.com/browse', headers=headers, cookies=cookies, timeout=15, **kw)
        
        cookie_header = '; '.join(f"{k}={v}" for k, v in cookies.items())
        headers['Cookie'] = cookie_header
        r = session.get('https://www.netflix.com/account/membership', headers=headers, timeout=15, **kw)

        if r.status_code != 200:
            return {"live": False, "status_code": r.status_code, "reason": "Dead (Status not 200)", "route": route}

        html = r.text
        if "account-membership-page" not in html and "membership" not in r.url:
            return {"live": False, "reason": "Redirected ke login/homepage (Dead cookie)", "route": route}

        # Extract plan
        if re.search(r'4K video resolution[^<]*?(?:spatial audio|ad-free)', html, re.I):
            plan = "Premium 4K"
        else:
            plan_match = re.search(r'data-uia="account-membership-page\+plan-card\+title"[^>]*>([^<]{1,40}?)<', html)
            plan = plan_match.group(1).strip() if plan_match else "Live (Standard/Basic)"

        # Extract payment date
        date_match = re.search(
            r'<h3[^>]*data-uia="account-membership-page\+payments-card\+title"[^>]*>Next payment</h3>[^<]*<p[^>]*data-uia="account-membership-page\+payments-card\+description"[^>]*>([^<]+?)</p>',
            html, re.DOTALL | re.I
        )
        billing = date_match.group(1).strip() if date_match else "N/A"

        # Extract country
        country_code = None
        for pat in (r'"countryOfSignup"\s*:\s*"([A-Za-z]{2})"', r'"currentCountry"\s*:\s*"([A-Za-z]{2})"', r'"memberCountry"\s*:\s*"([A-Za-z]{2})"', r'"paymentCountry"\s*:\s*"([A-Za-z]{2})"', r'"countryCode"\s*:\s*"([A-Za-z]{2})"'):
            m = re.search(pat, html)
            if m:
                country_code = m.group(1)
                break

        # Exportable Cookie-Editor array
        cookie_editor_json = [
            {"domain": ".netflix.com", "name": k, "path": "/", "secure": True, "httpOnly": True, "value": v}
            for k, v in cookies.items() if k in NETFLIX_COOKIE_NAMES
        ]

        return {
            "live": True,
            "plan": plan,
            "billing": billing,
            "country": normalize_country(country_code),
            "cookies": cookie_editor_json,
            "route": route
        }
    except Exception as e:
        return {"live": False, "reason": f"Request error: {str(e)}", "route": route}

HTML_PAGE = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Netflix Suite — NFToken & Account Checker</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root {
  --primary: #e50914;
  --primary-hover: #b80710;
  --bg: #0d0e12;
  --panel: #16181f;
  --panel-border: #262933;
  --panel-hover: #1e212b;
  --text: #f0f2f5;
  --text-muted: #8b92a5;
  --success: #10b981;
  --success-bg: rgba(16, 185, 129, 0.12);
  --error: #ef4444;
  --error-bg: rgba(239, 68, 68, 0.12);
  --warning: #f59e0b;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Plus Jakarta Sans', sans-serif;
  background-color: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 36px 16px 60px;
}
.app-container {
  width: 100%;
  max-width: 760px;
}
header {
  text-align: center;
  margin-bottom: 28px;
}
.brand-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(229, 9, 20, 0.15);
  color: #ff4d55;
  padding: 4px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  border: 1px solid rgba(229, 9, 20, 0.3);
}
h1 {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.8px;
  color: #fff;
  margin-bottom: 6px;
}
header p {
  color: var(--text-muted);
  font-size: 14px;
}

/* Tabs */
.tabs {
  display: flex;
  gap: 8px;
  background: #111318;
  padding: 4px;
  border-radius: 10px;
  border: 1px solid var(--panel-border);
  margin-bottom: 20px;
}
.tab-btn {
  flex: 1;
  padding: 10px 16px;
  background: transparent;
  border: 0;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  font-family: inherit;
}
.tab-btn.active {
  background: var(--panel-border);
  color: #fff;
}

/* Card */
.card {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: 14px;
  padding: 26px;
  box-shadow: 0 12px 36px rgba(0,0,0,0.4);
}
label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.input-wrap { position: relative; }
textarea {
  width: 100%;
  height: 140px;
  background: #0d0e12;
  color: #fff;
  border: 1px solid var(--panel-border);
  border-radius: 8px;
  padding: 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
}
textarea:focus {
  border-color: var(--primary);
}

.options-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(255,255,255,0.05);
}
.chk-label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  user-select: none;
}
.chk-label input {
  accent-color: var(--primary);
  width: 16px;
  height: 16px;
  cursor: pointer;
}
.badge-proxy {
  font-size: 11px;
  color: #4ade80;
  background: rgba(74, 222, 128, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  border: 1px solid rgba(74, 222, 128, 0.2);
  font-family: 'JetBrains Mono', monospace;
}

/* Buttons */
.btn-submit {
  width: 100%;
  margin-top: 16px;
  padding: 12px;
  background: var(--primary);
  color: #fff;
  border: 0;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: background 0.15s, transform 0.05s;
}
.btn-submit:hover {
  background: var(--primary-hover);
}
.btn-submit:active {
  transform: scale(0.99);
}
.btn-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Results */
.result-box {
  margin-top: 22px;
  display: none;
  border-radius: 10px;
  padding: 18px;
  font-size: 13px;
}
.result-box.success {
  background: var(--success-bg);
  border: 1px solid rgba(16, 185, 129, 0.3);
  color: #e6fffa;
}
.result-box.error {
  background: var(--error-bg);
  border: 1px solid rgba(239, 68, 68, 0.3);
  color: #fee2e2;
}

.res-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
  font-size: 15px;
  margin-bottom: 12px;
}
.pill {
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}
.pill-live { background: var(--success); color: #000; }
.pill-dead { background: var(--error); color: #fff; }

.link-field {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.link-input {
  flex: 1;
  background: #090a0d;
  border: 1px solid var(--panel-border);
  padding: 8px 12px;
  border-radius: 6px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  color: #7dd3fc;
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.btn-mini {
  padding: 8px 14px;
  background: #272a36;
  border: 1px solid #3c4052;
  color: #fff;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.btn-mini:hover { background: #333847; }

.grid-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin: 14px 0 8px;
}
.info-card {
  background: rgba(0,0,0,0.3);
  padding: 10px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.06);
}
.info-title { font-size: 11px; color: var(--text-muted); margin-bottom: 2px; text-transform: uppercase; }
.info-val { font-size: 14px; font-weight: 600; color: #fff; }

footer {
  margin-top: auto;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
  padding-top: 30px;
}
</style>
</head>
<body>

<div class="app-container">
  <header>
    <div class="brand-badge">⚡ Netflix Tool Suite</div>
    <h1>NFToken & Cookie Checker</h1>
    <p>Generate login link langsung atau validasi status langganan akun Netflix.</p>
  </header>

  <div class="tabs">
    <button class="tab-btn active" onclick="switchTab('nftoken')">🔗 NFToken Generator</button>
    <button class="tab-btn" onclick="switchTab('checker')">🛡️ Account Membership Checker</button>
  </div>

  <div class="card">
    <label>
      <span id="input-label">Cookie Netflix</span>
      <span style="font-weight:normal; font-size:11px;">Mendukung: Netscape / JSON / Raw Header</span>
    </label>
    
    <div class="input-wrap">
      <textarea id="cookie-input" placeholder="Paste NetflixId=...; SecureNetflixId=... atau format JSON/Netscape di sini"></textarea>
    </div>

    <div class="options-row">
      <label class="chk-label">
        <input type="checkbox" id="chk-proxy" checked>
        Pakai Proxy Webshare Rotasi
      </label>
      <span class="badge-proxy">20 Proxies Active</span>
    </div>

    <button id="btn-action" class="btn-submit" onclick="executeAction()">
      <span>Eksekusi</span>
    </button>

    <div id="output-box" class="result-box"></div>
  </div>

  <footer>
    Netflix Tool Suite &bull; Webshare Multi-Proxy Backend &bull; 2026
  </footer>
</div>

<script>
let currentMode = 'nftoken';

function switchTab(mode) {
  currentMode = mode;
  document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');

  const btn = document.getElementById('btn-action');
  const out = document.getElementById('output-box');
  out.style.display = 'none';

  if (mode === 'nftoken') {
    btn.innerHTML = '<span>Generate Login NFToken</span>';
    document.getElementById('input-label').innerText = 'Cookie Netflix (NetflixId)';
  } else {
    btn.innerHTML = '<span>Check Status Akun</span>';
    document.getElementById('input-label').innerText = 'Cookie Netflix (NetflixId / SecureNetflixId)';
  }
}

async function executeAction() {
  const cookie = document.getElementById('cookie-input').value.trim();
  const useProxy = document.getElementById('chk-proxy').checked;
  const btn = document.getElementById('btn-action');
  const out = document.getElementById('output-box');

  if (!cookie) {
    alert('Silakan masukkan cookie terlebih dahulu!');
    return;
  }

  btn.disabled = true;
  out.style.display = 'none';

  if (currentMode === 'nftoken') {
    btn.innerHTML = '<span>Mengambil NFToken via Netflix API...</span>';
    try {
      const res = await fetch('/api/token', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cookie, use_proxy: useProxy})
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'Gagal generate token');

      out.className = 'result-box success';
      out.innerHTML = `
        <div class="res-header">
          <span>NFToken Login Link Dibuat</span>
          <span class="pill pill-live">READY</span>
        </div>
        <div class="link-field">
          <a href="${data.url}" target="_blank" class="link-input" id="url-target">${data.url}</a>
          <button class="btn-mini" onclick="copyText('${data.url}')">Salin</button>
        </div>
        <div class="grid-info">
          <div class="info-card">
            <div class="info-title">Expired Time</div>
            <div class="info-val">${data.expires}</div>
          </div>
          <div class="info-card">
            <div class="info-title">Route Connection</div>
            <div class="info-val" style="font-size:12px;">${data.route}</div>
          </div>
        </div>
      `;
      out.style.display = 'block';
    } catch (err) {
      out.className = 'result-box error';
      out.innerHTML = `<div class="res-header"><span>Gagal</span><span class="pill pill-dead">ERROR</span></div><div>${err.message}</div>`;
      out.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>Generate Login NFToken</span>';
    }
  } else {
    btn.innerHTML = '<span>Memeriksa Membership ke Netflix...</span>';
    try {
      const res = await fetch('/api/check', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({cookie, use_proxy: useProxy})
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'Gagal check akun');

      if (data.live) {
        window.lastCookies = JSON.stringify(data.cookies, null, 2);
        out.className = 'result-box success';
        out.innerHTML = `
          <div class="res-header">
            <span>Akun Netflix LIVE / AKTIF</span>
            <span class="pill pill-live">LIVE</span>
          </div>
          <div class="grid-info">
            <div class="info-card">
              <div class="info-title">Plan / Paket</div>
              <div class="info-val">${data.plan}</div>
            </div>
            <div class="info-card">
              <div class="info-title">Next Billing Date</div>
              <div class="info-val">${data.billing}</div>
            </div>
            <div class="info-card">
              <div class="info-title">Negara Akun</div>
              <div class="info-val">${data.country}</div>
            </div>
            <div class="info-card">
              <div class="info-title">Route</div>
              <div class="info-val" style="font-size:12px;">${data.route}</div>
            </div>
          </div>
          <div style="margin-top:12px; display:flex; gap:8px;">
            <button class="btn-mini" onclick="copyCookies()">📋 Salin JSON Cookie (Cookie-Editor)</button>
          </div>
        `;
      } else {
        out.className = 'result-box error';
        out.innerHTML = `
          <div class="res-header">
            <span>Akun Netflix DEAD</span>
            <span class="pill pill-dead">DEAD</span>
          </div>
          <div><b>Alasan:</b> ${data.reason || 'Sesi cookie ditolak / expired.'}</div>
          <div style="margin-top:6px; font-size:11px; color:#aaa;">Route: ${data.route || 'Direct'}</div>
        `;
      }
      out.style.display = 'block';
    } catch (err) {
      out.className = 'result-box error';
      out.innerHTML = `<div class="res-header"><span>Gagal Memproses</span><span class="pill pill-dead">ERROR</span></div><div>${err.message}</div>`;
      out.style.display = 'block';
    } finally {
      btn.disabled = false;
      btn.innerHTML = '<span>Check Status Akun</span>';
    }
  }
}

function copyText(val) {
  navigator.clipboard.writeText(val);
  alert('Link berhasil disalin!');
}

function copyCookies() {
  if (window.lastCookies) {
    navigator.clipboard.writeText(window.lastCookies);
    alert('Cookie JSON berhasil disalin untuk Cookie-Editor!');
  }
}

// Inisialisasi awal
switchTab('nftoken');
</script>
</body>
</html>
"""

class ThreadingSimpleServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen)

        if self.path == "/api/token":
            try:
                payload = json.loads(body.decode("utf-8"))
                use_px = payload.get("use_proxy", True)
                url, expires, route = generate_nftoken(payload.get("cookie", ""), use_proxy=use_px)
                res_body = json.dumps({"url": url, "expires": expires, "route": route}).encode("utf-8")
                self.send_response(200)
            except Exception as e:
                res_body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res_body)

        elif self.path == "/api/check":
            try:
                payload = json.loads(body.decode("utf-8"))
                use_px = payload.get("use_proxy", True)
                result = check_netflix_membership(payload.get("cookie", ""), use_proxy=use_px)
                res_body = json.dumps(result).encode("utf-8")
                self.send_response(200)
            except Exception as e:
                res_body = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(res_body)
        else:
            self.send_response(404)
            self.end_headers()

def run():
    ThreadingSimpleServer.allow_reuse_address = True
    with ThreadingSimpleServer(("", PORT), Handler) as httpd:
        print(f"Server jalan di: http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run()
