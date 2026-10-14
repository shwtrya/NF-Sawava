import hashlib
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

def _get_token_secret():
    try:
        cfg = get_config()
        secret = cfg.get("db_encryption_key") or cfg.get("api_key") or "nf_sawava_session_secret"
        return secret.encode("utf-8") if isinstance(secret, str) else secret
    except Exception:
        return b"nf_sawava_session_secret_default"

def create_dashboard_session_token(ttl_seconds=604800):
    """Generates a secure, cryptographically signed token valid for ttl_seconds (default 7 days)."""
    exp = int(time.time() + ttl_seconds)
    nonce = secrets.token_hex(16)
    secret = _get_token_secret()
    payload = f"{exp}:{nonce}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    token = f"{exp}_{nonce}_{sig}"
    with dashboard_token_lock:
        now = time.time()
        expired = [t for t, e in active_dashboard_tokens.items() if e < now]
        for t in expired:
            active_dashboard_tokens.pop(t, None)
        active_dashboard_tokens[token] = exp
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

    now = time.time()
    # 1. Quick in-memory cache check
    with dashboard_token_lock:
        exp = active_dashboard_tokens.get(token)
        if exp:
            if exp > now:
                return True
            else:
                active_dashboard_tokens.pop(token, None)
                return False

    # 2. Cryptographic signature check (survives process restart)
    try:
        parts = token.split('_')
        if len(parts) == 3:
            exp_str, nonce, sig = parts
            exp = int(exp_str)
            if exp > now:
                secret = _get_token_secret()
                payload = f"{exp}:{nonce}".encode("utf-8")
                expected_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
                if hmac.compare_digest(sig, expected_sig):
                    with dashboard_token_lock:
                        active_dashboard_tokens[token] = exp
                    return True
    except Exception:
        pass

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

def check_dashboard_authorized(headers):
    """
    Returns True if:
    1. Request provides valid API key, OR
    2. Request provides valid Dashboard PIN session token, OR
    3. No dashboard_pin is set in config (public/open dashboard mode)
    """
    if check_api_key_authorized(headers):
        return True
    if check_dashboard_token_authorized(headers):
        return True
    try:
        cfg = get_config()
        if not cfg.get("dashboard_pin"):
            return True
    except Exception:
        pass
    return False
