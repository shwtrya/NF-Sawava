# -*- coding: utf-8 -*-
"""
NF-Sawava Suite Server
Modular Architecture Entrypoint
"""
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.server
import json
import logging
import os
import platform
import queue
import re
import socketserver
import sys
import threading
import time
import urllib.parse
from datetime import datetime

# ── Import Modular Subsystems ────────────────────────────────────────────────
from modules.config import (
    BASE_DIR, PORT, PROXIES_FILE, DB_FILE, CONFIG_FILE, LOG_FILE,
    API_URL, QUERY_PARAMS, BASE_HEADERS, COOKIE_KEYS, COUNTRY_CODE_NAMES,
    _recheck_mode, get_config, save_config, server_start_time
)
from modules.tls_engine import (
    create_tls_session, tls_request, TLSSessionWrapper,
    MODERN_TLS_PROFILES, get_recommended_impersonate, _map_curl_error,
    CURL_CFFI_AVAILABLE
)
from modules.detector import (
    extract_cookie_values, get_cookie_fingerprint, detect_universal_format
)
from modules.notifications import (
    send_telegram_alert, send_discord_alert,
    dispatch_live_notification, dispatch_bulk_notification
)
from modules.db import (
    get_db, queue_db_write, execute_db_write_sync,
    db_writer_worker, start_db_writer, flush_db_queue, init_db,
    save_history, get_history, export_history_csv, get_analytics, clear_history,
    decrypt_credential
)
from modules.sse import (
    register_sse_client, unregister_sse_client, broadcast_sse
)

from modules.batch_runner import (
    start_batch_job, get_job_state, stop_batch_job, list_recent_jobs
)
from modules.auth import (
    is_rate_limited, create_dashboard_session_token,
    check_dashboard_token_authorized, touch_api_key,
    check_api_key_authorized, check_authorized_client,
    check_dashboard_authorized
)
from modules import proxy_manager
from modules.proxy_manager import (
    proxy_lock,
    proxy_test_state, proxy_test_lock, proxy_cooldown, proxy_cooldown_lock,
    get_cached_proxy_states, update_cached_proxy_state,
    batch_update_cached_proxy_states, delete_from_proxy_cache,
    parse_single_proxy, load_proxies, check_proxy_health,
    test_single_proxy_func, stop_background_proxy_test,
    start_background_proxy_test, clean_dead_proxies_serverside,
    remove_proxies_flexible, proxy_health_worker, test_all_proxies_now,
    mark_proxy_cooldown, record_proxy_success, get_random_proxy,
    sync_provider_proxies
)
from modules.rechecker import recheck_history_item

from checkers.netflix import (
    check_netflix_membership, generate_nftoken, normalize_country
)
from checkers.disney import (
    check_disney_account, check_disney_cookie, extract_disney_refresh_token
)
from checkers.crunchyroll import (
    check_crunchyroll_account, check_crunchyroll_cookie, extract_crunchyroll_etp_rt
)
from checkers.spotify import (
    check_spotify_cookie, extract_spotify_sp_dc
)
from checkers.openai import (
    check_openai_cookie, extract_openai_session_token
)
from checkers.outlook import (
    check_outlook_account
)
from checkers.primevideo import (
    check_primevideo_cookie
)
from checkers.expressvpn import (
    check_expressvpn_account
)
from modules.proxy_auto_scraper import (
    run_auto_scrape, get_scraper_status, start_auto_scraper_thread
)

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
        elif path in ("/api/health", "/api/auth/status", "/api/proxies", "/api/dashboard-pin/status"):
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
        client_ip = self.client_address[0]

        if path in ("/", "/index.html"):
            html_file = os.path.join(os.path.dirname(__file__), "web", "index.html")
            if not os.path.exists(html_file):
                html_file = os.path.join(os.path.dirname(__file__), "index.html")
            if os.path.exists(html_file):
                with open(html_file, "r", encoding="utf-8") as f:
                    content = f.read().encode("utf-8")
            else:
                content = b"<h1>index.html not found</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' 'unsafe-eval' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; img-src 'self' data:; connect-src 'self' https://*.trycloudflare.com https://*.sawavaganteng.cloud https://cdn.jsdelivr.net")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)

        elif path in ("/admin", "/admin/", "/admin.html"):
            token_q = qs.get("token", [""])[0] or qs.get("key", [""])[0]
            req_headers = dict(self.headers)
            if token_q:
                req_headers["X-API-Key"] = token_q

            if check_authorized_client(req_headers):
                html_file = os.path.join(os.path.dirname(__file__), "web", "admin.html")
                if not os.path.exists(html_file):
                    html_file = os.path.join(os.path.dirname(__file__), "admin.html")
                if os.path.exists(html_file):
                    with open(html_file, "r", encoding="utf-8") as f:
                        content = f.read().encode("utf-8")
                else:
                    content = b"<h1>admin.html not found</h1>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
                return
            else:
                gate_html = """<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Gate - NF-Sawava Suite</title>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0a0c10; color:#e6edf3; font-family:'Plus Jakarta Sans',sans-serif; min-height:100vh; display:flex; align-items:center; justify-content:center; padding:20px; }
.card { background:linear-gradient(180deg,#13161c,#0d1117); border:1px solid #30363d; border-radius:16px; padding:32px; width:100%; max-width:420px; box-shadow:0 20px 40px rgba(0,0,0,0.6); text-align:center; }
.logo { font-size:32px; margin-bottom:12px; }
h1 { font-size:20px; font-weight:800; margin-bottom:8px; color:#fff; }
p { font-size:13px; color:#8b949e; margin-bottom:24px; line-height:1.5; }
input { width:100%; padding:14px 16px; background:#04070b; border:1px solid #30363d; border-radius:10px; color:#fff; font-family:'JetBrains Mono',monospace; font-size:14px; margin-bottom:16px; outline:none; transition:border 0.2s; text-align:center; }
input:focus { border-color:#e50914; box-shadow:0 0 0 3px rgba(229,9,20,0.2); }
button { width:100%; padding:14px; background:#e50914; color:#fff; border:none; border-radius:10px; font-weight:700; font-size:14px; cursor:pointer; transition:background 0.2s, transform 0.1s; }
button:hover { background:#f40612; }
button:active { transform:scale(0.98); }
.err { color:#f85149; font-size:12px; margin-top:12px; display:none; }
</style>
</head>
<body>
<div class="card">
  <div class="logo">🛡️</div>
  <h1>NF-Sawava Admin Gate</h1>
  <p>Panel administrasi terproteksi. Masukkan API Key atau Master PIN untuk membuka.</p>
  <form id="gate-form" onsubmit="handleLogin(event)">
    <input type="password" id="gate-key" placeholder="API Key / Master PIN..." autocomplete="current-password" autofocus required>
    <button type="submit" id="gate-btn">Buka Panel Admin</button>
  </form>
  <div id="gate-err" class="err">Kunci API / PIN tidak valid!</div>
</div>
<script>
async function handleLogin(e) {
  e.preventDefault();
  const k = document.getElementById('gate-key').value.trim();
  const btn = document.getElementById('gate-btn');
  const err = document.getElementById('gate-err');
  err.style.display = 'none';
  btn.disabled = true;
  btn.innerText = 'Memverifikasi...';
  try {
    const res = await fetch('/api/history?limit=1', {
      headers: { 'X-API-Key': k }
    });
    if (res.ok) {
      document.cookie = 'nf_api_key=' + encodeURIComponent(k) + '; path=/; max-age=2592000; SameSite=Strict';
      sessionStorage.setItem('NF_ADMIN_KEY', k);
      window.location.reload();
      return;
    }
  } catch(ex){}
  btn.disabled = false;
  btn.innerText = 'Buka Panel Admin';
  err.style.display = 'block';
}
</script>
</body>
</html>"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(gate_html.encode("utf-8"))
                return

        elif path == "/favicon.ico":
            fav = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"><rect width="24" height="24" rx="5" fill="#07090e"/><path d="M12 2L2 7l10 5 10-5-10-5Z" stroke="#e50914" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="m2 17 10 5 10-5" stroke="#06b6d4" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/><path d="m2 12 10 5 10-5" stroke="#3b82f6" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'''
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(fav)

        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):].lstrip("/\\")
            static_dir = os.path.abspath(os.path.join(BASE_DIR, "static"))
            safe_path = os.path.abspath(os.path.join(static_dir, rel_path))
            if safe_path.startswith(static_dir) and os.path.isfile(safe_path):
                ext = os.path.splitext(safe_path)[1].lower()
                mime_types = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".json": "application/json; charset=utf-8",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".ico": "image/x-icon",
                    ".woff2": "font/woff2",
                    ".woff": "font/woff",
                    ".ttf": "font/ttf"
                }
                c_type = mime_types.get(ext, "application/octet-stream")
                with open(safe_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", c_type)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(data)
                return
            else:
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"404 Not Found")
                return

        elif path == "/manifest.json":
            m_path = os.path.join(BASE_DIR, "web", "manifest.json")
            if not os.path.isfile(m_path):
                m_path = os.path.join(BASE_DIR, "manifest.json")
            if os.path.isfile(m_path):
                with open(m_path, "rb") as f:
                    m_data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(m_data)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        elif path == "/sw.js":
            sw_path = os.path.join(BASE_DIR, "web", "sw.js")
            if not os.path.isfile(sw_path):
                sw_path = os.path.join(BASE_DIR, "sw.js")
            if os.path.isfile(sw_path):
                with open(sw_path, "rb") as f:
                    sw_data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(sw_data)
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        elif path.startswith("/api/stream/bulk") or path in ("/api/stream", "/api/stream/bulk"):
            session_id = qs.get("session_id", ["default"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.flush()

            client_q = queue.Queue(maxsize=1000)
            register_sse_client(session_id, client_q)
            try:
                init_msg = json.dumps({"session_id": session_id, "status": "connected"})
                self.wfile.write(f"event: connected\ndata: {init_msg}\n\n".encode("utf-8"))
                self.wfile.flush()

                while True:
                    try:
                        ev_type, ev_data = client_q.get(timeout=15.0)
                        if isinstance(ev_data, (dict, list)):
                            ev_json = json.dumps(ev_data)
                        else:
                            ev_json = str(ev_data)
                        msg = f"event: {ev_type}\ndata: {ev_json}\n\n".encode("utf-8")
                        self.wfile.write(msg)
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, socketserver.socket.error):
                pass
            except Exception as sse_err:
                logging.debug(f"SSE client stream error: {sse_err}")
            finally:
                unregister_sse_client(session_id, client_q)
            return

        elif path == "/api/health":
            uptime = int(time.time() - server_start_time)
            with proxy_lock:
                h_proxies = len(proxy_manager.healthy_proxies)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            res = {
                "status": "healthy",
                "uptime_seconds": uptime,
                "timestamp": datetime.now().isoformat(),
                "healthy_proxies": h_proxies,
                "tls_engine": {
                    "available": CURL_CFFI_AVAILABLE,
                    "impersonation_profiles": MODERN_TLS_PROFILES,
                    "default_mode": "adaptive_rotation"
                }
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

        elif path == "/api/dashboard-pin/status":
            cfg = get_config()
            pin_set = bool(cfg.get("dashboard_pin", ""))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"enabled": pin_set}).encode("utf-8"))

        elif path.startswith("/api/bulk/status"):
            job_id = qs.get("job_id", [""])[0]
            st = get_job_state(job_id)
            if not st:
                self.send_response(404)
                res = json.dumps({"error": "Job not found"}).encode("utf-8")
            else:
                self.send_response(200)
                res = json.dumps(st).encode("utf-8")
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(res)
            return

        elif path == "/api/bulk/jobs":
            jobs = list_recent_jobs(15)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({"jobs": jobs}).encode("utf-8"))
            return

        elif path == "/api/proxies":
            # Load proxies outside proxy_lock to avoid lock inversion deadlock
            # (load_proxies acquires cached_proxies_lock -> proxy_lock)
            load_proxies()
            with proxy_lock:
                total_n = len(proxy_manager.all_tested_proxies)
                h_count = len(proxy_manager.healthy_proxies)
                d_count = len([p for p in proxy_manager.all_tested_proxies if p.get("status") == "FAIL"])
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
            # Rate limiting check: max 20 calls/min per client IP to prevent automated scraping
            if is_rate_limited(client_ip, max_requests=20, window_seconds=60, bucket="account_random"):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "30")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": "Rate limit exceeded: Terlalu banyak permintaan akun. Silakan coba sesaat lagi."
                }).encode("utf-8"))
                return

            # Security Authorization Check: Valid API Key OR Dashboard Session Token required (if PIN enabled)
            if not check_dashboard_authorized(self.headers):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": "Unauthorized: API Key atau Dashboard Session diperlukan untuk mengambil akun live."
                }).encode("utf-8"))
                return

            svc = qs.get("service", qs.get("type", ["netflix"]))[0].lower().strip()

            conn = get_db()
            c = conn.cursor()
            if svc in ('netflix', 'checker', 'single', 'bulk'):
                c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'netflix' AND status = 'LIVE' ORDER BY RANDOM() LIMIT 1;")
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
            elif svc in ('openai', 'chatgpt', 'gpt'):
                c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'openai' AND status IN ('LIVE', 'PREMIUM', 'FREE') ORDER BY RANDOM() LIMIT 1;")
            elif svc in ('primevideo', 'pv', 'amazon'):
                c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE type = 'primevideo' AND status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
            else:
                c.execute("SELECT id, type, status, email, raw_cookie, token_url, plan, country FROM history WHERE status IN ('LIVE', 'PREMIUM') ORDER BY RANDOM() LIMIT 1;")
            row = c.fetchone()
            conn.close()

            if row:
                r_id, r_type, r_status, r_email, r_cookie, r_token, r_plan, r_country = row
                # Ensure encrypted raw_cookie or token is cleanly decrypted for the user
                if r_cookie and str(r_cookie).startswith("enc:"):
                    r_cookie = decrypt_credential(r_cookie)
                if r_token and str(r_token).startswith("enc:"):
                    r_token = decrypt_credential(r_token)
                content_to_copy = r_cookie or r_token or r_email
                # Mask email for safe presentation
                email_masked = "-"
                if r_email and "@" in r_email:
                    parts = r_email.split("@", 1)
                    u, d = parts[0], parts[1]
                    masked_u = (u[:2] + "****" + u[-1:]) if len(u) > 3 else (u[:1] + "***")
                    email_masked = f"{masked_u}@{d}"
                elif r_email:
                    email_masked = r_email

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
                    "email_masked": email_masked,
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

        elif path == '/api/stats':
            # Public summary stats for main dashboard (no sensitive data)
            an = get_analytics()
            with proxy_lock:
                p_total = len(proxy_manager.all_tested_proxies) if proxy_manager.all_tested_proxies else 0
                p_healthy = len(proxy_manager.healthy_proxies)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({
                "status_counts": an.get("status_counts", {}),
                "services": an.get("services_detail", an.get("services", {})),
                "proxy": {"total": p_total, "healthy": p_healthy}
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
                'services': ['netflix', 'disney', 'disney-cookie', 'crunchyroll', 'crunchyroll-cookie', 'expressvpn', 'spotify', 'outlook', 'hotmail', 'openai'],
                'python': platform.python_version(),
                'uptime': int(time.time() - server_start_time)
            }).encode('utf-8'))

        elif path in ("/api/history", "/api/history/export_csv", "/api/analytics", "/api/proxies/detail", "/api/proxies/export", "/api/proxies/provider-config", "/api/notifications/config"):
            # API key or active Dashboard Session required for data/history endpoints
            if not check_authorized_client(self.headers):
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized: API Key or Dashboard Session required"}')
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
                self.send_header("Content-Disposition", f"attachment; filename=history_{int(time.time())}.csv")
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

                load_proxies()  # Pre-load outside lock to avoid deadlock
                now = time.time()
                with proxy_lock:
                    total_all = len(proxy_manager.all_tested_proxies)
                    healthy_all = len(proxy_manager.healthy_proxies)
                    dead_items = [p for p in proxy_manager.all_tested_proxies if p.get("status") in ("FAIL", "DEAD")]
                    dead_all = len(dead_items)
                    with proxy_cooldown_lock:
                        cooldown_items = [
                            p for p in proxy_manager.all_tested_proxies
                            if p.get("status") == "COOLDOWN"
                            or proxy_cooldown.get(p.get("proxy", ""), 0) > now
                            or p.get("cooldown_until", 0) > now
                        ]
                    cooldown_all = len(cooldown_items)
                    unverified_all = max(0, total_all - (healthy_all + dead_all + cooldown_all))
                    active_all = healthy_all if healthy_all > 0 else (total_all - dead_all)

                    if status_filter in ("OK", "LIVE"):
                        source_list = proxy_manager.healthy_proxies
                    elif status_filter in ("FAIL", "DEAD"):
                        source_list = dead_items
                    elif status_filter in ("COOLDOWN", "HOLD"):
                        source_list = cooldown_items
                    elif status_filter in ("UNVERIFIED", "UNTESTED", "READY"):
                        source_list = [p for p in proxy_manager.all_tested_proxies if p.get("status") in ("UNVERIFIED", "UNTESTED", "READY") and p not in cooldown_items]
                    else:
                        source_list = proxy_manager.all_tested_proxies

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
                    raw_items_page = filtered[start_idx:end_idx]

                    items_page = []
                    with proxy_cooldown_lock:
                        for p in raw_items_page:
                            p_copy = dict(p)
                            cd_end = max(p.get("cooldown_until", 0), proxy_cooldown.get(p.get("proxy", ""), 0))
                            rem = max(0, int(cd_end - now))
                            p_copy["cooldown_remaining"] = rem
                            if rem > 0:
                                p_copy["status"] = "COOLDOWN"
                            items_page.append(p_copy)

                with proxy_test_lock:
                    t_info = dict(proxy_test_state)

                avg_latency = 0
                if proxy_manager.healthy_proxies:
                    lats = [p.get("latency", 0) for p in proxy_manager.healthy_proxies if p.get("latency", 0) > 0]
                    if lats:
                        avg_latency = int(sum(lats) / len(lats))

                res_payload = {
                    "total": total_all,
                    "healthy": healthy_all,
                    "healthy_count": healthy_all,
                    "dead": dead_all,
                    "dead_count": dead_all,
                    "cooldown": cooldown_all,
                    "cooldown_count": cooldown_all,
                    "unverified": unverified_all,
                    "unverified_count": unverified_all,
                    "active": active_all,
                    "active_count": active_all,
                    "avg_latency": avg_latency,
                    "filtered_total": filtered_total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                    "testing": t_info.get("running", False),
                    "test_info": t_info,
                    "test_progress": t_info,
                    "items": items_page,
                    "proxies": items_page,
                    "list": items_page
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(res_payload).encode("utf-8"))

            elif path == "/api/proxies/provider-config":
                cfg = get_config()
                p_cfg = dict(cfg.get("proxy_provider", {}))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "provider": p_cfg}).encode("utf-8"))

            elif path == "/api/notifications/config":
                cfg = get_config()
                n_cfg = json.loads(json.dumps(cfg.get("notifications", {})))
                if "telegram" in n_cfg and n_cfg["telegram"].get("bot_token"):
                    tok = n_cfg["telegram"]["bot_token"]
                    n_cfg["telegram"]["bot_token_masked"] = (tok[:4] + "..." + tok[-4:]) if len(tok) > 8 else "***"
                    del n_cfg["telegram"]["bot_token"]
                if "discord" in n_cfg and n_cfg["discord"].get("webhook_url"):
                    wh = n_cfg["discord"]["webhook_url"]
                    n_cfg["discord"]["webhook_url_masked"] = (wh[:15] + "..." + wh[-6:]) if len(wh) > 25 else "***"
                    del n_cfg["discord"]["webhook_url"]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "notifications": n_cfg}).encode("utf-8"))

            elif path == "/api/proxies/export":
                mode = qs.get("mode", ["healthy"])[0].lower()
                load_proxies()  # Pre-load outside lock to avoid deadlock
                with proxy_lock:
                    p_list = list(proxy_manager.all_tested_proxies)
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
            admin_file = os.path.join(os.path.dirname(__file__), 'web', 'admin.html')
            if not os.path.exists(admin_file):
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
            if not os.path.isfile(req_file):
                req_file_web = os.path.realpath(os.path.join(safe_root, "web", clean_path))
                if os.path.isfile(req_file_web):
                    req_file = req_file_web
            allowed_public_files = {"index.html", "favicon.ico", "admin.html", "manifest.json", "sw.js"}
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
                    if ext == ".html":
                        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    else:
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
                    res = execute_db_write_sync("create_api_key", {
                        "key": new_key,
                        "label": label,
                        "created_at": now_str
                    })
                    result = res
                elif action == "revoke":
                    key_id = p.get("id")
                    if not key_id:
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(b'{"error": "Missing id"}')
                        return
                    execute_db_write_sync("revoke_api_key", {"id": key_id})
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
                    execute_db_write_sync("delete_api_key", {"id": key_id})
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
                    conn = get_db()
                    c = conn.cursor()
                    c.execute('SELECT COUNT(*) FROM history')
                    hist_count = c.fetchone()[0]
                    conn.close()
                    with proxy_lock:
                        proxy_count = len(proxy_manager.all_tested_proxies)
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

        elif self.path in ("/api/token", "/api/check", "/api/disney/check", "/api/crunchyroll/check", "/api/expressvpn/check", "/api/spotify/check", "/api/outlook/check", "/api/openai/check", "/api/primevideo/check", "/api/crunchyroll/cookie-check", "/api/disney/cookie-check", "/api/universal/detect", "/api/universal/parse", "/api/universal/check", "/api/bulk/start", "/api/bulk/stop", "/api/proxies/save", "/api/proxies/test", "/api/proxies/test/stop", "/api/proxies/test_single", "/api/proxies/add", "/api/proxies/remove", "/api/proxies/auto-scrape", "/api/proxies/scraper-status", "/api/proxies/provider-config", "/api/proxies/sync-provider", "/api/notifications/config", "/api/notifications/test", "/api/notifications/bulk-summary", "/api/history/clear", "/api/history/delete", "/api/history/recheck", "/api/system/reload", "/api/dashboard-pin/set", "/api/dashboard-pin/verify", "/api/dashboard-pin/remove"):
            rate_limit = 200 if self.path in ("/api/disney/check", "/api/crunchyroll/check", "/api/expressvpn/check", "/api/spotify/check", "/api/outlook/check", "/api/openai/check", "/api/primevideo/check", "/api/crunchyroll/cookie-check", "/api/disney/cookie-check", "/api/universal/detect", "/api/universal/parse", "/api/universal/check", "/api/bulk/start", "/api/bulk/stop") else 50
            if is_rate_limited(client_ip, max_requests=rate_limit, window_seconds=10, bucket="api"):
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", "5")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Too Many Requests. Rate limit exceeded."}')
                return

            # Checker endpoints are public; proxy management needs API key or Dashboard Session
            proxy_mgmt = {"/api/proxies/save", "/api/proxies/test", "/api/proxies/test/stop",
                          "/api/proxies/test_single", "/api/proxies/add", "/api/proxies/remove",
                          "/api/proxies/auto-scrape", "/api/proxies/scraper-status",
                          "/api/proxies/provider-config", "/api/proxies/sync-provider",
                          "/api/notifications/config", "/api/notifications/test",
                          "/api/history/clear", "/api/history/delete", "/api/history/recheck", "/api/system/reload",
                          "/api/dashboard-pin/set", "/api/dashboard-pin/remove"}
            if self.path in proxy_mgmt:
                if not check_authorized_client(self.headers):
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Unauthorized: API Key or Dashboard Session required"}')
                    return

            if self.path in ("/api/universal/detect", "/api/universal/parse"):
                try:
                    p = json.loads(body.decode("utf-8")) if body else {}
                    raw_text = p.get("text", "") or p.get("content", "") or p.get("cookie", "")
                    out = detect_universal_format(raw_text)
                    self.send_response(200)
                    res = json.dumps(out).encode("utf-8")
                except Exception as e:
                    self.send_response(400)
                    res = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)
                return

            if self.path == "/api/universal/check":
                try:
                    p = json.loads(body.decode("utf-8")) if body else {}
                    raw_item = p.get("item", "") or p.get("text", "") or p.get("cookie", "")
                    svc = (p.get("service", "") or "").lower().strip()
                    use_proxy = bool(p.get("use_proxy", True))

                    if not raw_item:
                        self.send_response(400)
                        res = json.dumps({"error": "No item/cookie/credential provided", "status": "ERROR"}).encode("utf-8")
                    else:
                        if not svc or svc == "unknown":
                            det = detect_universal_format(raw_item)
                            svc = det.get("service") or "netflix"

                        out = {}
                        if svc == "netflix":
                            out = check_netflix_membership(raw_item, use_proxy=use_proxy)
                        elif svc == "spotify":
                            out = check_spotify_cookie(raw_item, use_proxy=use_proxy)
                        elif svc == "openai":
                            out = check_openai_cookie(raw_item, use_proxy=use_proxy)
                        elif svc == "crunchyroll":
                            if ":" in raw_item[:100] and not raw_item.startswith("{"):
                                parts = raw_item.split(":", 1)
                                out = check_crunchyroll_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy)
                            else:
                                out = check_crunchyroll_cookie(raw_item, use_proxy=use_proxy)
                        elif svc == "disney":
                            if ":" in raw_item[:100] and not raw_item.startswith("{"):
                                parts = raw_item.split(":", 1)
                                out = check_disney_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy)
                            else:
                                out = check_disney_cookie(raw_item, use_proxy=use_proxy)
                        elif svc in ("outlook", "hotmail"):
                            parts = raw_item.split(":", 1)
                            if len(parts) == 2:
                                out = check_outlook_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy)
                            else:
                                out = {"status": "ERROR", "error": "Invalid email:password format"}
                        elif svc == "expressvpn":
                            parts = raw_item.split(":", 1)
                            if len(parts) == 2:
                                def _evpn_proxy_fn():
                                    prx, label, raw = get_random_proxy()
                                    return (prx.get('http') or prx.get('https')) if prx else None
                                out = check_expressvpn_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy, get_proxy_fn=_evpn_proxy_fn, save_history_fn=save_history)
                            else:
                                out = {"status": "ERROR", "error": "Invalid email:password format"}
                        elif svc == "primevideo":
                            out = check_primevideo_cookie(raw_item, use_proxy=use_proxy, get_proxy_fn=get_random_proxy, cooldown_fn=mark_proxy_cooldown, save_fn=save_history, session_fn=lambda: create_tls_session(impersonate="primevideo"))
                        else:
                            out = check_netflix_membership(raw_item, use_proxy=use_proxy)

                        status = out.get("status", "ERROR")
                        if status in ("LIVE", "OK"):
                            try:
                                dispatch_live_notification(out, raw_item, svc)
                            except Exception as ex_notif:
                                logging.debug(f"Notification error: {ex_notif}")

                        self.send_response(200)
                        res = json.dumps({"service": svc, "status": status, "result": out}).encode("utf-8")
                except Exception as e:
                    self.send_response(500)
                    res = json.dumps({"error": str(e), "status": "ERROR"}).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)
                return

            if self.path == "/api/bulk/start":
                try:
                    p = json.loads(body.decode("utf-8")) if body else {}
                    service = p.get("service", "universal")
                    items = p.get("items", [])
                    use_proxy = bool(p.get("use_proxy", True))
                    concurrency = int(p.get("concurrency", 3))
                    send_notif = bool(p.get("send_notification", True))

                    job_id, err = start_batch_job(service, items, use_proxy=use_proxy, concurrency=concurrency, send_notif=send_notif)
                    if err:
                        self.send_response(400)
                        res = json.dumps({"error": err, "status": "ERROR"}).encode("utf-8")
                    else:
                        self.send_response(200)
                        res = json.dumps({"status": "RUNNING", "job_id": job_id, "total": len(items)}).encode("utf-8")
                except Exception as e:
                    self.send_response(500)
                    res = json.dumps({"error": str(e), "status": "ERROR"}).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)
                return

            if self.path == "/api/bulk/stop":
                try:
                    p = json.loads(body.decode("utf-8")) if body else {}
                    job_id = p.get("job_id", "")
                    ok = stop_batch_job(job_id)
                    self.send_response(200 if ok else 404)
                    res = json.dumps({"success": ok, "job_id": job_id}).encode("utf-8")
                except Exception as e:
                    self.send_response(500)
                    res = json.dumps({"error": str(e)}).encode("utf-8")
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)
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
                    broadcast_sse("check_result", out, session_id=p.get("session_id"))
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

            elif self.path == "/api/openai/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cookie = p.get("cookie", "").strip()
                    if not cookie:
                        raise ValueError("Cookie wajib diisi")
                    out = check_openai_cookie(cookie, use_proxy=p.get("use_proxy", True))
                    res = json.dumps(out).encode("utf-8")
                    self.send_response(200)
                except Exception as e:
                    res = json.dumps({"status": "ERROR", "reason": str(e)}).encode("utf-8")
                    self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(res)

            elif self.path == "/api/primevideo/check":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cookie = p.get("cookie", "").strip()
                    if not cookie:
                        raise ValueError("Cookie wajib diisi")
                    out = check_primevideo_cookie(
                        cookie,
                        use_proxy=p.get("use_proxy", True),
                        get_proxy_fn=get_random_proxy,
                        cooldown_fn=mark_proxy_cooldown,
                        save_fn=save_history,
                        session_fn=lambda: create_tls_session(impersonate="primevideo")
                    )
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
                        proxy_manager.healthy_proxies.clear()
                        proxy_manager.all_tested_proxies.clear()
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
                        proxy_manager.healthy_proxies.clear()
                        proxy_manager.all_tested_proxies.clear()
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
                            proxy_manager.healthy_proxies.clear()
                            proxy_manager.all_tested_proxies.clear()
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

            elif self.path == "/api/proxies/auto-scrape":
                # Trigger manual auto-scrape cycle
                def _run_scrape():
                    run_auto_scrape()
                    # Reload proxy pool after scrape
                    load_proxies(force_reload=True)
                threading.Thread(target=_run_scrape, daemon=True).start()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "message": "Auto-scrape started in background"}).encode("utf-8"))

            elif self.path == "/api/proxies/scraper-status":
                status = get_scraper_status()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(status).encode("utf-8"))

            elif self.path == "/api/proxies/provider-config":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cfg = get_config()
                    current = cfg.get("proxy_provider", {})
                    for k in ("enabled", "provider_name", "api_url", "auto_sync_interval_minutes"):
                        if k in p:
                            current[k] = p[k]
                    cfg["proxy_provider"] = current
                    save_config(cfg)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "provider": current}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/proxies/sync-provider":
                try:
                    res = sync_provider_proxies()
                    self.send_response(200 if res.get("ok") else 400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(res).encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/notifications/config":
                try:
                    p = json.loads(body.decode("utf-8"))
                    cfg = get_config()
                    cur_notifs = cfg.get("notifications", {})
                    if "telegram" in p:
                        tg = p["telegram"]
                        cur_tg = cur_notifs.setdefault("telegram", {})
                        if "enabled" in tg: cur_tg["enabled"] = bool(tg["enabled"])
                        if "bot_token" in tg and tg["bot_token"]: cur_tg["bot_token"] = str(tg["bot_token"]).strip()
                        if "chat_id" in tg: cur_tg["chat_id"] = str(tg["chat_id"]).strip()
                        if "notify_on_live" in tg: cur_tg["notify_on_live"] = bool(tg["notify_on_live"])
                        if "notify_on_bulk_finish" in tg: cur_tg["notify_on_bulk_finish"] = bool(tg["notify_on_bulk_finish"])

                    if "discord" in p:
                        dc = p["discord"]
                        cur_dc = cur_notifs.setdefault("discord", {})
                        if "enabled" in dc: cur_dc["enabled"] = bool(dc["enabled"])
                        if "webhook_url" in dc and dc["webhook_url"]: cur_dc["webhook_url"] = str(dc["webhook_url"]).strip()
                        if "notify_on_live" in dc: cur_dc["notify_on_live"] = bool(dc["notify_on_live"])
                        if "notify_on_bulk_finish" in dc: cur_dc["notify_on_bulk_finish"] = bool(dc["notify_on_bulk_finish"])

                    cfg["notifications"] = cur_notifs
                    save_config(cfg)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/notifications/test":
                try:
                    p = json.loads(body.decode("utf-8")) if body else {}
                    target = p.get("target", "all").lower()
                    results = {}

                    if target in ("all", "telegram"):
                        tg_ok, tg_msg = send_telegram_alert(
                            "🧪 <b>[NF-Sawava Test Alert]</b>\nNotifikasi Telegram Bot berhasil terhubung ke NF-Sawava Suite!"
                        )
                        results["telegram"] = {"ok": tg_ok, "message": tg_msg}

                    if target in ("all", "discord"):
                        fields = [
                            {"name": "Status", "value": "Connected", "inline": True},
                            {"name": "Environment", "value": "Production", "inline": True}
                        ]
                        dc_ok, dc_msg = send_discord_alert(
                            "🧪 [NF-Sawava Test Alert]",
                            "Webhook Discord berhasil terhubung ke NF-Sawava Suite!",
                            fields=fields,
                            color=0x3B82F6
                        )
                        results["discord"] = {"ok": dc_ok, "message": dc_msg}

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True, "results": results}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/notifications/bulk-summary":
                try:
                    p = json.loads(body.decode("utf-8")) if body else {}
                    dispatch_bulk_notification(p)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                except Exception as e:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))

            elif self.path == "/api/system/reload":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status": "reloading"}')
                def _do_exit():
                    time.sleep(0.5)
                    flush_db_queue(timeout=2.0)
                    os._exit(0)
                threading.Thread(target=_do_exit, daemon=True).start()

            elif self.path == "/api/dashboard-pin/set":
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    payload = {}
                new_pin = str(payload.get("pin", "")).strip()
                if not new_pin or len(new_pin) < 4:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "reason": "PIN minimal 4 karakter"}).encode("utf-8"))
                else:
                    import hashlib
                    pin_hash = hashlib.sha256(new_pin.encode()).hexdigest()
                    cfg = get_config()
                    cfg["dashboard_pin"] = pin_hash
                    save_config(cfg)
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "message": "Dashboard PIN berhasil diset"}).encode("utf-8"))

            elif self.path == "/api/dashboard-pin/verify":
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    payload = {}
                pin_input = str(payload.get("pin", "")).strip()
                cfg = get_config()
                stored_hash = cfg.get("dashboard_pin", "")
                if not stored_hash:
                    # No PIN set, always pass
                    session_token = create_dashboard_session_token()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Set-Cookie", f"nf_dashboard_token={session_token}; Path=/; Max-Age=604800; SameSite=Lax")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "valid": True, "token": session_token}).encode("utf-8"))
                else:
                    import hashlib
                    input_hash = hashlib.sha256(pin_input.encode()).hexdigest()
                    valid = (input_hash == stored_hash)
                    session_token = create_dashboard_session_token() if valid else ""
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    if valid and session_token:
                        self.send_header("Set-Cookie", f"nf_dashboard_token={session_token}; Path=/; Max-Age=604800; SameSite=Lax")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "ok", "valid": valid, "token": session_token}).encode("utf-8"))

            elif self.path == "/api/dashboard-pin/remove":
                cfg = get_config()
                cfg["dashboard_pin"] = ""
                save_config(cfg)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "message": "Dashboard PIN dihapus"}).encode("utf-8"))

            elif self.path == "/api/history/delete":
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    payload = {}
                record_id = payload.get("id")
                if not record_id:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"status": "error", "reason": "Missing id"}')
                else:
                    try:
                        res = execute_db_write_sync("delete_history_id", {"id": int(record_id)})
                        deleted = res.get("deleted", 0)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        resp = {"status": "ok", "deleted": deleted}
                        self.wfile.write(json.dumps(resp).encode("utf-8"))
                    except Exception as e:
                        self.send_response(500)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "error", "reason": str(e)}).encode("utf-8"))

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

            elif self.path == "/api/history/recheck":
                try:
                    payload = json.loads(body.decode("utf-8")) if body else {}
                except Exception:
                    payload = {}
                use_proxy = payload.get("use_proxy", True)

                if payload.get("bulk"):
                    # Bulk recheck: query DB directly, no separate API call needed
                    filter_status = payload.get("status", "all")
                    filter_type = payload.get("type", "all")
                    query = "SELECT id FROM history WHERE raw_cookie IS NOT NULL AND raw_cookie != ''"
                    params_q = []
                    if filter_status and filter_status != "all":
                        query += " AND status = ?"
                        params_q.append(filter_status)
                    if filter_type and filter_type != "all":
                        query += " AND type = ?"
                        params_q.append(filter_type)
                    query += " ORDER BY id DESC"

                    conn = get_db()
                    c = conn.cursor()
                    c.execute(query, params_q)
                    ids = [r[0] for r in c.fetchall()]
                    conn.close()

                    if not ids:
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"total": 0, "ok": 0, "changed": 0, "to_live": 0, "to_dead": 0, "errors": 0}).encode("utf-8"))
                    else:
                        from concurrent.futures import ThreadPoolExecutor
                        def _do(rid):
                            try:
                                return recheck_history_item(rid, use_proxy=use_proxy)
                            except Exception as e:
                                return {"id": rid, "error": str(e)}
                        with ThreadPoolExecutor(max_workers=5) as pool:
                            results = list(pool.map(_do, ids))
                        ok = 0; changed = 0; to_live = 0; to_dead = 0; errs = 0
                        for r in results:
                            if r.get("error"):
                                errs += 1
                            else:
                                ok += 1
                                if r.get("old_status") != r.get("new_status"):
                                    changed += 1
                                    if r.get("new_status") == "LIVE": to_live += 1
                                    if r.get("new_status") == "DEAD": to_dead += 1
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"total": len(ids), "ok": ok, "changed": changed, "to_live": to_live, "to_dead": to_dead, "errors": errs}).encode("utf-8"))

                elif payload.get("ids") and isinstance(payload["ids"], list):
                    record_ids = payload["ids"]
                    from concurrent.futures import ThreadPoolExecutor
                    def _do_one(rid):
                        try:
                            return recheck_history_item(int(rid), use_proxy=use_proxy)
                        except Exception as e:
                            return {"id": rid, "error": str(e)}
                    with ThreadPoolExecutor(max_workers=5) as pool:
                        results = list(pool.map(_do_one, record_ids))
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"results": results}).encode("utf-8"))

                elif payload.get("id"):
                    try:
                        result = recheck_history_item(int(payload["id"]), use_proxy=use_proxy)
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps(result).encode("utf-8"))
                    except Exception as e:
                        self.send_response(500)
                        self.send_header("Content-Type", "application/json")
                        self.send_cors_headers()
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_cors_headers()
                    self.end_headers()
                    self.wfile.write(b'{"error": "Missing id, ids, or bulk"}')
        else:
            self.send_response(404)
            self.send_cors_headers()
            self.end_headers()

def session_vault_worker():
    """Background worker: automatically renews and validates expiring active sessions in DB."""
    while True:
        time.sleep(1800)
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT id, raw_cookie FROM history WHERE type = 'netflix' AND status = 'LIVE' AND raw_cookie != '' ORDER BY id DESC LIMIT 25")
            rows = c.fetchall()
            conn.close()

            for row_id, raw_cookie in rows:
                try:
                    if raw_cookie and str(raw_cookie).startswith("enc:"):
                        raw_cookie = decrypt_credential(raw_cookie)
                    t_url, a_url, tv_url, tok, exp, route = generate_nftoken(raw_cookie, use_proxy=True)
                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    queue_db_write("update_history_token", {
                        "id": row_id,
                        "token_url": t_url,
                        "created_at": now
                    })
                    logging.info(f"Session Vault: renewed token for history ID {row_id}")
                except Exception as e:
                    err = str(e).lower()
                    if any(k in err for k in ("mati", "invalid", "tidak ditemukan", "401", "403")):
                        queue_db_write("update_history_status", {
                            "id": row_id,
                            "status": "DEAD"
                        })
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
    start_auto_scraper_thread()  # Auto-scrape fresh proxies every 6h

    # Prevent duplicate zombie processes on Windows
    socketserver.TCPServer.allow_reuse_address = False if os.name == "nt" else True
    server = ThreadingSimpleServer(("", PORT), Handler)
    print(f"Server jalan: http://localhost:{PORT}")
    logging.info(f"Server started on port {PORT}")
    try:
        server.serve_forever()
    finally:
        flush_db_queue(timeout=5.0)

if __name__ == "__main__":
    run()
