import atexit
import base64
import csv
import hashlib
import io
import logging
import queue
import sqlite3
import threading
import time
from datetime import datetime
from cryptography.fernet import Fernet
from modules.config import DB_FILE, _recheck_mode, get_config, save_config
from modules.detector import get_cookie_fingerprint
from modules.notifications import dispatch_live_notification

_fernet_cipher = None
_fernet_lock = threading.Lock()

def get_db_cipher():
    global _fernet_cipher
    if _fernet_cipher is not None:
        return _fernet_cipher
    with _fernet_lock:
        if _fernet_cipher is not None:
            return _fernet_cipher
        cfg = get_config()
        key = cfg.get("db_encryption_key")
        if not key:
            seed = cfg.get("api_key") or cfg.get("dashboard_pin") or "nf_sawava_db_secret_seed"
            key = base64.urlsafe_b64encode(hashlib.sha256(seed.encode("utf-8")).digest()).decode("utf-8")
            cfg["db_encryption_key"] = key
            try:
                save_config(cfg)
            except Exception as ex_cfg:
                logging.debug(f"Save db_encryption_key note: {ex_cfg}")
        _fernet_cipher = Fernet(key.encode("utf-8") if isinstance(key, str) else key)
        return _fernet_cipher

def encrypt_credential(text: str) -> str:
    if not text:
        return text
    if str(text).startswith("enc:"):
        return text
    try:
        cipher = get_db_cipher()
        enc = cipher.encrypt(str(text).encode("utf-8")).decode("utf-8")
        return f"enc:{enc}"
    except Exception as e:
        logging.warning(f"Credential encryption fallback: {e}")
        return text

def decrypt_credential(text: str) -> str:
    if not text:
        return text
    if not str(text).startswith("enc:"):
        return text
    try:
        cipher = get_db_cipher()
        return cipher.decrypt(str(text)[4:].encode("utf-8")).decode("utf-8")
    except Exception as e:
        logging.warning(f"Credential decryption fallback: {e}")
        return text

db_lock = threading.Lock()
db_write_queue = queue.Queue(maxsize=50000)
_db_writer_stop_event = threading.Event()
_db_writer_thread = None

def get_db():
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def queue_db_write(action, data):
    """Enqueue an asynchronous, non-blocking DB write task."""
    try:
        db_write_queue.put_nowait((action, data, None, None))
    except queue.Full:
        logging.error("Database write queue full (50,000 items)! Emergency drop.")

def execute_db_write_sync(action, data, timeout=10.0):
    """Execute a DB write task synchronously via the dedicated writer thread."""
    done_event = threading.Event()
    result_box = {}
    try:
        db_write_queue.put((action, data, done_event, result_box), timeout=timeout)
        if not done_event.wait(timeout=timeout):
            raise TimeoutError(f"Database write timed out for action '{action}'")
        if not result_box.get("ok", False):
            err = result_box.get("error", "Unknown DB error")
            raise RuntimeError(f"Database write failed: {err}")
        return result_box.get("result", {})
    except Exception as e:
        logging.error(f"Sync DB write error ({action}): {e}")
        raise

def _process_single_db_task(cursor, conn, task):
    action, data, done_event, result_box = task
    try:
        if action == "save_history":
            p = data
            key = p.get("key")
            raw_cookie = p.get("raw_cookie", "")
            raw_cookie_enc = encrypt_credential(raw_cookie)
            existing = None
            if key:
                cursor.execute('SELECT id, plan, billing, country, token_url FROM history WHERE cookie_key = ? ORDER BY id DESC LIMIT 1', (key,))
                existing = cursor.fetchone()
            if not existing and raw_cookie:
                cursor.execute('SELECT id, plan, billing, country, token_url FROM history WHERE raw_cookie = ? OR raw_cookie = ? ORDER BY id DESC LIMIT 1', (raw_cookie, raw_cookie_enc))
                existing = cursor.fetchone()

            if existing:
                existing_id, ex_plan, ex_billing, ex_country, ex_token = existing
                final_plan = p["plan"] if p["plan"] else ex_plan
                final_billing = p["billing"] if p["billing"] else (ex_billing if p["status"] != 'DEAD' else '')
                final_country = p["country"] if p["country"] else ex_country
                final_token = p["token_url"] if p["token_url"] else (ex_token if p["status"] in ('LIVE', 'HOLD', 'FREE') else '')

                cursor.execute('''
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
                    p["now"], p["entry_type"], p["status"], final_plan, final_billing,
                    final_country, p["route"], final_token, raw_cookie_enc, key, p["email"],
                    existing_id
                ))
                if key:
                    cursor.execute('DELETE FROM history WHERE cookie_key = ? AND id != ?', (key, existing_id))
                logging.info(f"Update history [ID {existing_id}]: [{p['entry_type']}] {p['status']} - Plan: {final_plan} - Country: {final_country}")
            else:
                cursor.execute('''
                    INSERT INTO history (created_at, type, status, plan, billing, country, route, token_url, raw_cookie, cookie_key, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    p["now"], p["entry_type"], p["status"], p["plan"], p["billing"], p["country"],
                    p["route"], p["token_url"], raw_cookie_enc, key, p["email"]
                ))
                logging.info(f"Save history: [{p['entry_type']}] {p['status']} - Plan: {p['plan']} - Country: {p['country']}")

        elif action == "update_proxy_state":
            p = data
            fc_val = 0 if p["fail_count"] is None else p["fail_count"]
            sc_val = 0 if p["success_count"] is None else p["success_count"]
            cu_val = 0.0 if p["cooldown_until"] is None else p["cooldown_until"]
            cursor.execute("""
                INSERT INTO proxy_cache (proxy_key, status, latency, last_tested, fail_count, success_count, cooldown_until)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(proxy_key) DO UPDATE SET
                    status=excluded.status,
                    latency=CASE WHEN excluded.latency > 0 THEN excluded.latency ELSE proxy_cache.latency END,
                    last_tested=excluded.last_tested,
                    fail_count=CASE WHEN ? IS NOT NULL THEN excluded.fail_count ELSE proxy_cache.fail_count END,
                    success_count=CASE WHEN ? IS NOT NULL THEN excluded.success_count ELSE proxy_cache.success_count END,
                    cooldown_until=CASE WHEN ? IS NOT NULL THEN excluded.cooldown_until ELSE proxy_cache.cooldown_until END
            """, (
                p["proxy_key"], p["status"], p["latency"], p["now"],
                fc_val, sc_val, cu_val,
                p["fail_count"], p["success_count"], p["cooldown_until"]
            ))

        elif action == "batch_update_proxy_states":
            items = data.get("items", [])
            if items:
                cursor.executemany("""
                    INSERT INTO proxy_cache (proxy_key, status, latency, last_tested)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(proxy_key) DO UPDATE SET
                        status=excluded.status,
                        latency=excluded.latency,
                        last_tested=excluded.last_tested
                """, items)

        elif action == "delete_proxy_cache":
            keys = data.get("keys", [])
            batch_size = 500
            for i in range(0, len(keys), batch_size):
                chunk = keys[i:i+batch_size]
                placeholders = ",".join(["?"] * len(chunk))
                cursor.execute(f"DELETE FROM proxy_cache WHERE proxy_key IN ({placeholders})", chunk)

        elif action == "proxy_cooldown":
            p = data
            cursor.execute("""
                INSERT INTO proxy_cache (proxy_key, status, latency, last_tested, fail_count, cooldown_until)
                VALUES (?, 'COOLDOWN', 0, ?, 1, ?)
                ON CONFLICT(proxy_key) DO UPDATE SET
                    status='COOLDOWN',
                    fail_count=COALESCE(proxy_cache.fail_count, 0) + 1,
                    cooldown_until=?,
                    last_tested=?
            """, (p["key"], p["now"], p["until"], p["until"], p["now"]))

        elif action == "proxy_success":
            p = data
            lat = p.get("latency", 0)
            cursor.execute("""
                UPDATE proxy_cache
                SET status='OK',
                    latency=CASE WHEN ? > 0 THEN ? ELSE latency END,
                    success_count=COALESCE(success_count, 0) + 1,
                    fail_count=0,
                    cooldown_until=0,
                    last_tested=?
                WHERE proxy_key=? OR proxy_key=?
            """, (lat, lat, p["now"], p["key"], p.get("proxy_url", "")))

        elif action == "touch_api_key":
            cursor.execute('UPDATE api_keys SET last_used = ? WHERE id = ?', (data["last_used"], data["id"]))

        elif action == "update_history_status":
            p = data
            if "created_at" in p:
                cursor.execute('UPDATE history SET status = ?, created_at = ? WHERE id = ?', (p["status"], p["created_at"], p["id"]))
            else:
                cursor.execute('UPDATE history SET status = ? WHERE id = ?', (p["status"], p["id"]))

        elif action == "update_history_token":
            p = data
            cursor.execute('UPDATE history SET token_url = ?, created_at = ? WHERE id = ?', (p["token_url"], p["created_at"], p["id"]))

        elif action == "delete_history_id":
            cursor.execute('DELETE FROM history WHERE id = ?', (data["id"],))
            if result_box is not None:
                result_box["result"] = {"deleted": cursor.rowcount}
                result_box["ok"] = True

        elif action == "clear_history":
            only_dead = data.get("only_dead", False)
            if only_dead:
                cursor.execute('DELETE FROM history WHERE status IN ("DEAD", "ERROR", "BAD", "LOCKED", "PHONE_LOCKED")')
                logging.info("Deleted only DEAD/ERROR/BAD/LOCKED history records.")
            else:
                cursor.execute('DELETE FROM history')
                logging.info("History database cleared completely.")
            if result_box is not None:
                result_box["result"] = {"deleted": cursor.rowcount}
                result_box["ok"] = True

        elif action == "create_api_key":
            cursor.execute('INSERT INTO api_keys (key, label, created_at, is_active) VALUES (?, ?, ?, 1)',
                           (data["key"], data["label"], data["created_at"]))
            new_id = cursor.lastrowid
            if result_box is not None:
                result_box["result"] = {"id": new_id, "key": data["key"], "label": data["label"], "created_at": data["created_at"]}
                result_box["ok"] = True

        elif action == "revoke_api_key":
            cursor.execute('UPDATE api_keys SET is_active = 0 WHERE id = ?', (data["id"],))
            if result_box is not None:
                result_box["result"] = {"ok": True, "revoked": data["id"]}
                result_box["ok"] = True

        elif action == "delete_api_key":
            cursor.execute('DELETE FROM api_keys WHERE id = ?', (data["id"],))
            if result_box is not None:
                result_box["result"] = {"ok": True, "deleted": data["id"]}
                result_box["ok"] = True

        if result_box is not None and "ok" not in result_box:
            result_box["ok"] = True

    except Exception as ex:
        if result_box is not None:
            result_box["ok"] = False
            result_box["error"] = str(ex)
        logging.error(f"Error executing DB task '{action}': {ex}")
        raise
    finally:
        if done_event is not None:
            done_event.set()

def db_writer_worker():
    writer_conn = None
    try:
        writer_conn = sqlite3.connect(DB_FILE, timeout=60.0)
        writer_conn.execute("PRAGMA journal_mode=WAL;")
        writer_conn.execute("PRAGMA synchronous=NORMAL;")
        writer_conn.execute("PRAGMA busy_timeout=60000;")
        writer_conn.execute("PRAGMA cache_size=10000;")
        writer_conn.execute("PRAGMA temp_store=MEMORY;")
        cursor = writer_conn.cursor()

        while not _db_writer_stop_event.is_set() or not db_write_queue.empty():
            try:
                try:
                    first_task = db_write_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                batch = [first_task]
                while len(batch) < 50:
                    try:
                        next_task = db_write_queue.get_nowait()
                        batch.append(next_task)
                    except queue.Empty:
                        break

                for task in batch:
                    try:
                        _process_single_db_task(cursor, writer_conn, task)
                    except Exception as te:
                        logging.error(f"Error processing db write task: {te}")
                    finally:
                        db_write_queue.task_done()

                writer_conn.commit()

            except Exception as e:
                logging.error(f"DB writer worker loop error: {e}")
                if writer_conn:
                    try:
                        writer_conn.rollback()
                    except Exception:
                        pass
                time.sleep(0.05)

    finally:
        if writer_conn:
            try:
                writer_conn.commit()
                writer_conn.close()
            except Exception:
                pass

def start_db_writer():
    global _db_writer_thread
    if _db_writer_thread and _db_writer_thread.is_alive():
        return
    _db_writer_stop_event.clear()
    _db_writer_thread = threading.Thread(target=db_writer_worker, daemon=True, name="DBWriterThread")
    _db_writer_thread.start()
    logging.info("SQLite Asynchronous Write Worker started.")

def flush_db_queue(timeout=5.0):
    """Wait for all pending database writes to finish committing."""
    try:
        db_write_queue.join()
    except Exception as e:
        logging.error(f"Error flushing DB queue: {e}")

atexit.register(flush_db_queue)

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_FILE, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA cache_size=10000;")
        conn.execute("PRAGMA temp_store=MEMORY;")
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
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_type_status ON history(type, status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_status ON history(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_type ON history(type)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_created_at ON history(created_at DESC)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_history_email ON history(email)")

        c.execute('''
            CREATE TABLE IF NOT EXISTS proxy_cache (
                proxy_key TEXT PRIMARY KEY,
                status TEXT,
                latency INTEGER DEFAULT 0,
                last_tested REAL DEFAULT 0,
                fail_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                cooldown_until REAL DEFAULT 0,
                service_tags TEXT DEFAULT ''
            )
        ''')
        c.execute("PRAGMA table_info(proxy_cache)")
        p_cols = [r[1] for r in c.fetchall()]
        if "fail_count" not in p_cols:
            c.execute("ALTER TABLE proxy_cache ADD COLUMN fail_count INTEGER DEFAULT 0")
        if "success_count" not in p_cols:
            c.execute("ALTER TABLE proxy_cache ADD COLUMN success_count INTEGER DEFAULT 0")
        if "cooldown_until" not in p_cols:
            c.execute("ALTER TABLE proxy_cache ADD COLUMN cooldown_until REAL DEFAULT 0")
        if "service_tags" not in p_cols:
            c.execute("ALTER TABLE proxy_cache ADD COLUMN service_tags TEXT DEFAULT ''")
        c.execute("CREATE INDEX IF NOT EXISTS idx_proxy_status ON proxy_cache(status)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_proxy_last_tested ON proxy_cache(last_tested)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_proxy_cooldown ON proxy_cache(cooldown_until)")

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

        c.execute('SELECT COUNT(*) FROM api_keys')
        if c.fetchone()[0] == 0:
            cfg = get_config()
            master_key = cfg.get('api_key', '')
            if master_key:
                c.execute('INSERT INTO api_keys (key, label, created_at, is_active) VALUES (?, ?, ?, 1)',
                          (master_key, 'Master Key', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

        conn.commit()
        conn.close()
    start_db_writer()

def save_history(entry_type, status, plan='', billing='', country='', route='', token_url='', raw_cookie='', email=''):
    if getattr(_recheck_mode, 'active', False):
        return
    try:
        key = get_cookie_fingerprint(raw_cookie)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        queue_db_write("save_history", {
            "entry_type": entry_type,
            "status": status,
            "plan": plan,
            "billing": billing,
            "country": country,
            "route": route,
            "token_url": token_url,
            "raw_cookie": raw_cookie,
            "key": key,
            "email": email,
            "now": now
        })
        if status and str(status).upper() == 'LIVE':
            dispatch_live_notification(entry_type, email, plan, country, route)
    except Exception as e:
        logging.error(f"Error enqueuing history save: {e}")

def get_history(limit=50, offset=0, search='', status='', plan='', entry_type=''):
    conn = get_db()
    try:
        c = conn.cursor()
        where_parts = []
        params = []

        if search:
            s_clean = search.strip()
            where_parts.append('(country LIKE ? OR billing LIKE ? OR plan LIKE ? OR email LIKE ? OR raw_cookie LIKE ?)')
            params.extend([f'%{s_clean}%', f'%{s_clean}%', f'%{s_clean}%', f'%{s_clean}%', f'%{s_clean}%'])
        if status:
            where_parts.append('status = ?')
            params.append(status)
        if entry_type:
            where_parts.append('type = ?')
            params.append(entry_type)
        if plan:
            p_upper = plan.upper()
            if p_upper in ('PREMIUM', '4K'):
                where_parts.append('(plan LIKE "%4K%" OR plan LIKE "%ULTRA%" OR plan LIKE "%PREMIUM%")')
            elif p_upper == 'STANDARD':
                where_parts.append('(plan LIKE "%STANDARD%" OR plan LIKE "%STANDAR%")')
            elif p_upper == 'BASIC':
                where_parts.append('(plan LIKE "%BASIC%" OR plan LIKE "%DASAR%")')
            elif p_upper == 'MOBILE':
                where_parts.append('(plan LIKE "%MOBILE%" OR plan LIKE "%PONSEL%")')
            elif p_upper == 'SPOTIFY':
                where_parts.append('(plan LIKE "%Spotify%")')
            elif p_upper == 'DISNEY':
                where_parts.append('(plan LIKE "%Disney%")')
            elif p_upper == 'CRUNCHYROLL':
                where_parts.append('(plan LIKE "%Crunchyroll%")')
            elif p_upper == 'EXPRESSVPN':
                where_parts.append('(plan LIKE "%ExpressVPN%")')
            elif p_upper in ('OPENAI', 'CHATGPT', 'GPT'):
                where_parts.append('(plan LIKE "%ChatGPT%")')
            elif p_upper == 'FAMILY':
                where_parts.append('(plan LIKE "%Family%" OR plan LIKE "%Duo%")')
            elif p_upper == 'STUDENT':
                where_parts.append('(plan LIKE "%Student%")')
            else:
                where_parts.append('plan LIKE ?')
                params.append(f'%{plan}%')

        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

        count_query = 'SELECT COUNT(*) FROM history' + where_clause
        c.execute(count_query, params)
        total = c.fetchone()[0]

        query = 'SELECT id, created_at, type, status, plan, billing, country, route, token_url, raw_cookie, email FROM history' + where_clause + ' ORDER BY id DESC LIMIT ? OFFSET ?'
        c.execute(query, params + [limit, offset])
        rows = c.fetchall()

        items = [
            {
                "id": r[0], "created_at": r[1], "type": r[2], "status": r[3],
                "plan": r[4], "billing": r[5], "country": r[6], "route": r[7],
                "token_url": r[8], "raw_cookie": decrypt_credential(r[9]) if r[9] else "",
                "email": r[10] or ""
            }
            for r in rows
        ]
        return {"total": total, "items": items}
    finally:
        conn.close()

def export_history_csv(search='', status='', plan='', entry_type=''):
    conn = get_db()
    try:
        c = conn.cursor()
        where_parts = []
        params = []
        if search:
            s_clean = search.strip()
            where_parts.append('(country LIKE ? OR billing LIKE ? OR plan LIKE ? OR email LIKE ? OR raw_cookie LIKE ?)')
            params.extend([f'%{s_clean}%', f'%{s_clean}%', f'%{s_clean}%', f'%{s_clean}%', f'%{s_clean}%'])
        if status:
            where_parts.append('status = ?')
            params.append(status)
        if entry_type:
            where_parts.append('type = ?')
            params.append(entry_type)
        if plan:
            p_upper = plan.upper()
            if p_upper in ('PREMIUM', '4K'):
                where_parts.append('(plan LIKE "%4K%" OR plan LIKE "%ULTRA%" OR plan LIKE "%PREMIUM%")')
            elif p_upper == 'STANDARD':
                where_parts.append('(plan LIKE "%STANDARD%" OR plan LIKE "%STANDAR%")')
            elif p_upper == 'BASIC':
                where_parts.append('(plan LIKE "%BASIC%" OR plan LIKE "%DASAR%")')
            elif p_upper == 'MOBILE':
                where_parts.append('(plan LIKE "%MOBILE%" OR plan LIKE "%PONSEL%")')
            elif p_upper == 'SPOTIFY':
                where_parts.append('(plan LIKE "%Spotify%")')
            elif p_upper == 'DISNEY':
                where_parts.append('(plan LIKE "%Disney%")')
            elif p_upper == 'CRUNCHYROLL':
                where_parts.append('(plan LIKE "%Crunchyroll%")')
            elif p_upper == 'EXPRESSVPN':
                where_parts.append('(plan LIKE "%ExpressVPN%")')
            elif p_upper in ('OPENAI', 'CHATGPT', 'GPT'):
                where_parts.append('(plan LIKE "%ChatGPT%")')
            elif p_upper == 'FAMILY':
                where_parts.append('(plan LIKE "%Family%" OR plan LIKE "%Duo%")')
            elif p_upper == 'STUDENT':
                where_parts.append('(plan LIKE "%Student%")')
            else:
                where_parts.append('plan LIKE ?')
                params.append(f'%{plan}%')
        where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
        query = 'SELECT id, created_at, type, status, plan, billing, country, route, token_url, raw_cookie, email FROM history' + where_clause + ' ORDER BY id DESC'
        c.execute(query, params)
        rows = c.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Waktu", "Service", "Status", "Plan", "Billing", "Negara", "Route", "Token URL", "Raw Cookie", "Email"])
        for r in rows:
            r_list = list(r)
            if r_list[9]:
                r_list[9] = decrypt_credential(r_list[9])
            safe_row = []
            for cell in r_list:
                s = str(cell) if cell is not None else ""
                if s and s[0] in ("=", "+", "-", "@", "\t", "\r", "\n"):
                    s = "'" + s
                safe_row.append(s)
            writer.writerow(safe_row)
        return output.getvalue()
    finally:
        conn.close()

def migrate_encrypt_existing_history():
    """Migrate any unencrypted credentials in history table to Fernet encrypted format."""
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute("SELECT id, raw_cookie FROM history WHERE raw_cookie IS NOT NULL AND raw_cookie != '' AND raw_cookie NOT LIKE 'enc:%'")
        rows = c.fetchall()
        if not rows:
            return 0
        updated = 0
        for rid, raw in rows:
            enc = encrypt_credential(raw)
            c.execute("UPDATE history SET raw_cookie = ? WHERE id = ?", (enc, rid))
            updated += 1
        conn.commit()
        logging.info(f"Encrypted {updated} historical credential rows.")
        return updated
    except Exception as e:
        logging.error(f"Credential migration note: {e}")
        return 0
    finally:
        conn.close()

def get_analytics():
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT status, COUNT(*) FROM history GROUP BY status')
        status_counts = dict(c.fetchall())
        c.execute('SELECT country, COUNT(*) FROM history WHERE country != "" AND country != "Unknown" GROUP BY country ORDER BY COUNT(*) DESC LIMIT 8')
        country_counts = dict(c.fetchall())
        c.execute('SELECT plan, COUNT(*) FROM history WHERE (status = "LIVE" OR status = "HOLD") AND plan != "" GROUP BY plan ORDER BY COUNT(*) DESC LIMIT 6')
        plan_counts = dict(c.fetchall())

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

        c.execute(
            "SELECT DATE(created_at) AS day, COUNT(*) AS cnt "
            "FROM history WHERE created_at >= DATE('now', '-7 days') "
            "GROUP BY DATE(created_at) ORDER BY day"
        )
        daily_rows = c.fetchall()
        daily_stats = [{"date": r[0], "count": r[1]} for r in daily_rows]

        total_checks = sum(status_counts.values()) if status_counts else 0
        live_total = sum(v for k, v in status_counts.items() if k in ('LIVE', 'PREMIUM', 'FREE'))
        hit_rate = (live_total / total_checks) if total_checks > 0 else 0

        services_flat = {k: v.get("checks", 0) for k, v in services.items()}

        return {
            "status_counts": status_counts,
            "country_counts": country_counts,
            "countries": country_counts,
            "plan_counts": plan_counts,
            "services": services_flat,
            "services_detail": services,
            "daily_stats": daily_stats,
            "hit_rate": hit_rate
        }
    finally:
        conn.close()

def clear_history(only_dead=False):
    try:
        execute_db_write_sync("clear_history", {"only_dead": only_dead})
    except Exception as e:
        logging.error(f"Error in clear_history: {e}")
        raise
