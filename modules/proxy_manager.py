import concurrent.futures
import json
import logging
import os
import random
import requests
import threading
import time
import urllib.request
from modules.config import PROXIES_FILE, _recheck_mode, get_config
from modules.db import get_db, queue_db_write
from modules.sse import broadcast_sse

healthy_proxies = []
all_tested_proxies = []
proxy_lock = threading.Lock()

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

proxy_cooldown = {}
proxy_cooldown_lock = threading.Lock()

def get_cached_proxy_states():
    try:
        conn = get_db()
        try:
            c = conn.cursor()
            c.execute("SELECT proxy_key, status, latency, last_tested, fail_count, success_count, cooldown_until, service_tags FROM proxy_cache")
            rows = c.fetchall()
        finally:
            conn.close()
        now = time.time()
        res = {}
        for r in rows:
            k, st, lat, lt = r[0], r[1], r[2], r[3]
            fc = r[4] or 0
            sc = r[5] or 0
            cu = r[6] or 0.0
            tags = r[7] or ""
            if cu > now:
                actual_st = "COOLDOWN"
            elif st == "COOLDOWN" and cu <= now:
                actual_st = "OK"
            else:
                actual_st = st
            res[k] = {
                "status": actual_st,
                "latency": lat,
                "last_tested": lt,
                "fail_count": fc,
                "success_count": sc,
                "cooldown_until": cu,
                "service_tags": tags
            }
        return res
    except Exception as e:
        logging.error(f"Error reading proxy_cache: {e}")
        return {}

def update_cached_proxy_state(proxy_key, status, latency=0, fail_count=None, success_count=None, cooldown_until=None):
    if not proxy_key or getattr(_recheck_mode, 'active', False):
        return
    now = time.time()
    queue_db_write("update_proxy_state", {
        "proxy_key": proxy_key,
        "status": status,
        "latency": latency,
        "now": now,
        "fail_count": fail_count,
        "success_count": success_count,
        "cooldown_until": cooldown_until
    })

def batch_update_cached_proxy_states(items):
    if not items or getattr(_recheck_mode, 'active', False):
        return
    now = time.time()
    valid_items = [(k, s, l, now) for (k, s, l) in items if k]
    if valid_items:
        queue_db_write("batch_update_proxy_states", {
            "items": valid_items
        })

def delete_from_proxy_cache(keys):
    if not keys:
        return
    queue_db_write("delete_proxy_cache", {
        "keys": list(keys)
    })

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

    actual_scheme = scheme or "http"

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
            res_file = os.path.join(os.path.dirname(PROXIES_FILE), "netflix_residential_proxies.txt")
            if os.path.exists(res_file):
                try:
                    with open(res_file, "r", encoding="utf-8", errors="ignore") as rf:
                        for r_idx, r_line in enumerate(rf):
                            r_item = parse_single_proxy(r_line)
                            if r_item:
                                r_item["id"] = -(r_idx + 1)
                                r_item["is_residential"] = True
                                r_item["status"] = "OK"  # Residential proxy default ready
                                res.append(r_item)
                except Exception as ex_rf:
                    logging.debug(f"Residential proxy load note: {ex_rf}")

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
                            item["fail_count"] = cached.get("fail_count", 0)
                            item["success_count"] = cached.get("success_count", 0)
                            item["cooldown_until"] = cached.get("cooldown_until", 0)
                            item["service_tags"] = cached.get("service_tags", "")
                        else:
                            item["status"] = "UNVERIFIED"
                            item["latency"] = 0
                            item["last_tested"] = 0
                            item["fail_count"] = 0
                            item["success_count"] = 0
                            item["cooldown_until"] = 0
                            item["service_tags"] = ""
                        res.append(item)
            cached_proxies = res
            cached_proxies_mtime = mtime
            now = time.time()
            with proxy_lock:
                all_tested_proxies = list(res)
                healthy_proxies = [
                    p for p in res
                    if p.get("status") == "OK"
                    and p.get("cooldown_until", 0) <= now
                    and proxy_cooldown.get(p.get("proxy", ""), 0) <= now
                ]
            return [dict(p) for p in res]
    except Exception as e:
        logging.error(f"Error loading proxies: {e}")
        return []

def check_proxy_health(p, timeout=(5.0, 8.0), retries=1):
    prx = p.get("proxy") if isinstance(p, dict) else str(p)
    if not prx:
        return False, 0
    proxies = {"http": prx, "https": prx}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }
    health_targets = [
        "https://httpbin.org/status/200",
        "https://www.google.com/generate_204",
    ]
    for attempt in range(retries + 1):
        target = health_targets[attempt % len(health_targets)]
        t0 = time.time()
        try:
            to = timeout if attempt == 0 else (6.0, 10.0)
            r = requests.get(target, proxies=proxies, timeout=to, verify=False, headers=headers)
            if r.status_code in (200, 204, 301, 302, 404):
                latency = int((time.time() - t0) * 1000)
                return True, latency
        except Exception:
            pass
        if attempt < retries:
            time.sleep(0.3)
    return False, 0

def test_single_proxy_func(proxy_str):
    global healthy_proxies, all_tested_proxies
    item = parse_single_proxy(proxy_str)
    if not item:
        item = {"raw": proxy_str, "proxy": f"http://{proxy_str}", "line": proxy_str, "latency": 0, "status": "UNVERIFIED"}
    ok, lat = check_proxy_health(item, timeout=(5.0, 10.0), retries=2)
    item["status"] = "OK" if ok else "FAIL"
    item["latency"] = lat if ok else 0
    k = item.get("line") or item.get("proxy") or item.get("raw")
    update_cached_proxy_state(k, item["status"], item["latency"])

    load_proxies()
    with proxy_lock:
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
            load_proxies()
            with proxy_lock:
                current_pool = list(all_tested_proxies)
            
            if mode == "untested":
                candidates = [p for p in current_pool if p.get("status") in ("UNVERIFIED", "UNTESTED", "READY")]
                if not candidates:
                    candidates = current_pool
            elif mode == "dead":
                candidates = [p for p in current_pool if p.get("status") == "FAIL"]
            else:
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
                    if proxy_test_state["tested"] % 10 == 0:
                        broadcast_sse("proxy_progress", dict(proxy_test_state))
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
                broadcast_sse("proxy_progress", dict(proxy_test_state))

    threading.Thread(target=_worker, daemon=True).start()
    lim_label = "semua" if (not limit or limit <= 0) else f"{limit}"
    return True, f"Menjalankan benchmark test untuk {lim_label} proxy dengan high-concurrency engine..."

def clean_dead_proxies_serverside():
    global healthy_proxies, all_tested_proxies
    load_proxies()
    with proxy_lock:
        dead_keys = set()
        for p in all_tested_proxies:
            if p.get("status") == "FAIL":
                if p.get("line"): dead_keys.add(p["line"].strip())
                if p.get("raw"): dead_keys.add(p["raw"].strip())
                if p.get("proxy"): dead_keys.add(p["proxy"].strip())

        if not dead_keys:
            return 0, len(all_tested_proxies)

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
    try:
        with proxy_lock:
            h_len = len(healthy_proxies)
        if h_len < 10:
            start_background_proxy_test(limit=250, mode="untested")
    except Exception as e:
        logging.error(f"Proxy warmup error: {e}")

    while True:
        try:
            time.sleep(180)

            with proxy_test_lock:
                if proxy_test_state.get("running"):
                    continue

            load_proxies()
            with proxy_lock:
                all_p = list(all_tested_proxies)

            if not all_p:
                continue

            healthy_pool = [p for p in all_p if p.get("status") == "OK"]
            healthy_pool.sort(key=lambda x: x.get("last_tested", 0))
            sample_healthy = healthy_pool[:25]

            dead_pool = [p for p in all_p if p.get("status") == "FAIL"]
            dead_pool.sort(key=lambda x: x.get("last_tested", 0))
            sample_dead = dead_pool[:5]

            untested_pool = [p for p in all_p if p.get("status") in ("UNVERIFIED", "UNTESTED", "READY")]
            sample_untested = untested_pool[:20]

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

            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
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

def mark_proxy_cooldown(proxy_url, duration=300):
    if not proxy_url:
        return
    now = time.time()
    until = now + duration
    with proxy_cooldown_lock:
        proxy_cooldown[proxy_url] = until
    item = parse_single_proxy(proxy_url)
    k = item.get("line") or item.get("proxy") or proxy_url
    queue_db_write("proxy_cooldown", {
        "key": k,
        "now": now,
        "until": until
    })

def record_proxy_success(proxy_url, latency=0):
    if not proxy_url:
        return
    item = parse_single_proxy(proxy_url)
    k = item.get("line") or item.get("proxy") or proxy_url
    with proxy_cooldown_lock:
        if proxy_url in proxy_cooldown:
            del proxy_cooldown[proxy_url]
    now = time.time()
    queue_db_write("proxy_success", {
        "key": k,
        "proxy_url": proxy_url,
        "latency": latency,
        "now": now
    })

def get_random_proxy():
    global healthy_proxies, all_tested_proxies
    now = time.time()
    load_proxies()
    with proxy_lock:
        if healthy_proxies:
            pool = list(healthy_proxies)
        else:
            pool = [p for p in all_tested_proxies if p.get("status") not in ("FAIL", "DEAD")]
            if not pool and all_tested_proxies:
                pool = list(all_tested_proxies)
    if not pool:
        return None, None, None

    with proxy_cooldown_lock:
        valid_pool = [
            p for p in pool
            if proxy_cooldown.get(p.get("proxy", ""), 0) <= now
            and p.get("cooldown_until", 0) <= now
        ]
    if not valid_pool:
        valid_pool = sorted(pool, key=lambda x: proxy_cooldown.get(x.get("proxy", ""), 0))[:5]

    def _proxy_score(p):
        succ = p.get("success_count", 0)
        fail = p.get("fail_count", 0)
        lat = p.get("latency", 0) or 400
        rate = (succ + 1.0) / (succ + fail + 2.0)
        return (rate * 1000.0) / (lat + 100.0)

    scored = sorted(valid_pool, key=_proxy_score, reverse=True)
    top_candidates = scored[:max(1, len(scored) // 3)]
    choice = random.choice(top_candidates)
    lat_info = f" ({choice.get('latency', 0)}ms)" if choice.get("latency") else ""
    return {"http": choice["proxy"], "https": choice["proxy"]}, f"{choice['raw']}{lat_info}", choice["proxy"]

def sync_provider_proxies():
    cfg = get_config()
    provider_cfg = cfg.get("proxy_provider", {})
    api_url = provider_cfg.get("api_url", "").strip()
    if not api_url:
        return {"ok": False, "error": "Provider API URL is not configured"}

    headers = {
        "User-Agent": "NF-Sawava-Suite/3.0 (Proxy Provider Sync)"
    }
    api_key = provider_cfg.get("api_key", "").strip()
    if api_key:
        headers["Authorization"] = f"Token {api_key}"

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "").lower()
            raw_body = resp.read().decode("utf-8", errors="ignore")

        new_proxies = []
        if "application/json" in content_type or raw_body.strip().startswith(("{", "[")):
            try:
                data = json.loads(raw_body)
                if isinstance(data, dict):
                    results = data.get("results") or data.get("proxies") or data.get("data") or []
                    for item in results:
                        if isinstance(item, dict):
                            host = item.get("proxy_address") or item.get("ip") or item.get("host")
                            port = item.get("port")
                            user = item.get("username") or item.get("user")
                            pwd = item.get("password") or item.get("pass")
                            if host and port:
                                if user and pwd:
                                    new_proxies.append(f"{host}:{port}:{user}:{pwd}")
                                else:
                                    new_proxies.append(f"{host}:{port}")
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, str):
                            new_proxies.append(item.strip())
                        elif isinstance(item, dict):
                            host = item.get("proxy_address") or item.get("ip") or item.get("host")
                            port = item.get("port")
                            user = item.get("username")
                            pwd = item.get("password")
                            if host and port:
                                if user and pwd:
                                    new_proxies.append(f"{host}:{port}:{user}:{pwd}")
                                else:
                                    new_proxies.append(f"{host}:{port}")
            except Exception as e:
                logging.debug(f"JSON parse error during provider sync, falling back to text: {e}")

        if not new_proxies:
            for line in raw_body.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    parsed = parse_single_proxy(line)
                    if parsed:
                        new_proxies.append(line)

        if not new_proxies:
            return {"ok": False, "error": "No valid proxies could be extracted from provider response"}

        existing_lines = set()
        if os.path.exists(PROXIES_FILE):
            with open(PROXIES_FILE, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    l = line.strip()
                    if l:
                        existing_lines.add(l)

        added = 0
        with open(PROXIES_FILE, "a", encoding="utf-8") as f:
            for p in new_proxies:
                if p not in existing_lines:
                    f.write(p + "\n")
                    existing_lines.add(p)
                    added += 1

        load_proxies(force_reload=True)
        return {
            "ok": True,
            "added": added,
            "total_provider": len(new_proxies),
            "total_local": len(existing_lines),
            "message": f"Successfully synced {added} new proxies from provider"
        }
    except Exception as e:
        logging.error(f"Error syncing provider proxies: {e}")
        return {"ok": False, "error": str(e)}
