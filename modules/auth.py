import hmac
import logging
import secrets
import threading
import time
from datetime import datetime
from modules.config import get_config
from modules.db import get_db, queue_db_write

rate_limit_lock = threading.Lock()
ip_request_history = {}  # key -> list of timestamps

active_dashboard_tokens = {}
dashboard_token_lock = threading.Lock()
_api_key_last_touched = {}  # key_id -> timestamp

def is_rate_limited(ip, max_requests=40, window_seconds=10, bucket="default"):
    if not ip:
        return False
    key = f"{bucket}:{ip}"
    now = time.time()
    with rate_limit_lock:
        if len(ip_request_history) > 2000:
            stale = [k for k, values in ip_request_history.items()
                     if not values or now - values[-1] > 300]
            for stale_key in stale:
                ip_request_history.pop(stale_key, None)
        timestamps = ip_request_history.get(key, [])
        timestamps = [t for t in timestamps if now - t < window_seconds]
        if len(timestamps) >= max_requests:
            ip_request_history[key] = timestamps
            return True
        timestamps.append(now)
        ip_request_history[key] = timestamps
        return False

def create_dashboard_session_token(ttl_seconds=86400):
    token = secrets.token_hex(24)
    with dashboard_token_lock:
        now = time.time()
        expired = [t for t, exp in active_dashboard_tokens.items() if exp < now]
        for t in expired:
            active_dashboard_tokens.pop(t, None)
        active_dashboard_tokens[token] = now + ttl_seconds
    return token

def _extract_cookie_val(headers, name):
    cookie_hdr = headers.get('Cookie', '') or headers.get('cookie', '')
    if not cookie_hdr:
        return ''
    for part in cookie_hdr.split(';'):
        part = part.strip()
        if part.startswith(name + '='):
            return part[len(name) + 1:].strip()
    return ''

def check_dashboard_token_authorized(headers):
    token = headers.get('X-Dashboard-Token') or ''
    if not token:
        auth = headers.get('Authorization', '')
        if auth.startswith('Token '):
            token = auth[6:].strip()
    if not token:
        token = _extract_cookie_val(headers, 'nf_dashboard_token')
    if not token:
        return False
    with dashboard_token_lock:
        exp = active_dashboard_tokens.get(token)
        if exp and exp > time.time():
            return True
        elif exp:
            active_dashboard_tokens.pop(token, None)
    return False

def touch_api_key(key_id):
    now = time.time()
    last = _api_key_last_touched.get(key_id, 0)
    if now - last > 60:
        _api_key_last_touched[key_id] = now
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        queue_db_write("touch_api_key", {
            "id": key_id,
            "last_used": now_str
        })

def check_api_key_authorized(headers):
    key = headers.get('X-API-Key') or ''
    if not key:
        auth = headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            key = auth[7:].strip()
    if not key:
        key = _extract_cookie_val(headers, 'nf_api_key')
    if not key:
        return False

    try:
        cfg = get_config()
        master_key = cfg.get('api_key', '')
        if master_key and hmac.compare_digest(key, master_key):
            return True
    except Exception:
        pass

    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT id FROM api_keys WHERE key = ? AND is_active = 1', (key,))
        row = c.fetchone()
        conn.close()
        if row:
            touch_api_key(row[0])
            return True
    except Exception:
        logging.error("Error checking API key authorization")
    return False

def check_authorized_client(headers):
    """Returns True if request has valid API key OR valid Dashboard PIN session token."""
    if check_api_key_authorized(headers):
        return True
    if check_dashboard_token_authorized(headers):
        return True
    return False
