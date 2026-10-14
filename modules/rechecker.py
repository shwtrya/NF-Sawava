import logging
from datetime import datetime
from checkers.netflix import check_netflix_membership
from checkers.disney import check_disney_account, check_disney_cookie
from checkers.crunchyroll import check_crunchyroll_account, check_crunchyroll_cookie
from checkers.spotify import check_spotify_cookie
from checkers.openai import check_openai_cookie
from checkers.outlook import check_outlook_account
from checkers.expressvpn import check_expressvpn_account
from checkers.primevideo import check_primevideo_cookie
from modules.config import _recheck_mode
from modules.db import get_db, queue_db_write, save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown
from modules.tls_engine import create_tls_session

def recheck_history_item(record_id, use_proxy=True):
    """Re-check a history record's cookie/credential to update its status (LIVE/DEAD/HOLD)."""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, type, status, raw_cookie, email FROM history WHERE id = ?', (record_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"error": "Record not found", "id": record_id}

    rec_id, rec_type, old_status, raw_cookie, rec_email = row
    rec_type = (rec_type or "").lower()
    if not raw_cookie:
        return {"error": "No raw cookie/credential stored for this record", "id": rec_id}

    new_status = "ERROR"
    out = {}
    _recheck_mode.active = True
    try:
        if rec_type in ('netflix', 'single', 'bulk'):
            out = check_netflix_membership(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type == 'disney' and ':' not in raw_cookie[:100]:
            out = check_disney_cookie(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type == 'disney':
            parts = raw_cookie.split(':', 1)
            if len(parts) == 2:
                out = check_disney_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy)
            else:
                out = check_disney_cookie(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type == 'crunchyroll' and ':' not in raw_cookie[:100]:
            out = check_crunchyroll_cookie(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type == 'crunchyroll':
            parts = raw_cookie.split(':', 1)
            if len(parts) == 2:
                out = check_crunchyroll_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy)
            else:
                out = check_crunchyroll_cookie(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type == 'spotify':
            out = check_spotify_cookie(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type == 'openai':
            out = check_openai_cookie(raw_cookie, use_proxy=use_proxy)
            new_status = out.get('status', 'ERROR')
        elif rec_type in ('outlook', 'hotmail'):
            parts = raw_cookie.split(':', 1)
            if len(parts) == 2:
                out = check_outlook_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy)
                new_status = out.get('status', 'ERROR')
            else:
                return {"error": "Invalid credential format for outlook", "id": rec_id}
        elif rec_type == 'expressvpn':
            parts = raw_cookie.split(':', 1)
            if len(parts) == 2:
                def _evpn_proxy_fn():
                    prx, label, raw = get_random_proxy()
                    if prx:
                        return prx.get('http') or prx.get('https')
                    return None
                out = check_expressvpn_account(parts[0].strip(), parts[1].strip(), use_proxy=use_proxy, get_proxy_fn=_evpn_proxy_fn, save_history_fn=save_history)
                new_status = out.get('status', 'ERROR')
            else:
                return {"error": "Invalid credential format for expressvpn", "id": rec_id}
        elif rec_type == 'primevideo':
            out = check_primevideo_cookie(raw_cookie, use_proxy=use_proxy, get_proxy_fn=get_random_proxy, cooldown_fn=mark_proxy_cooldown, save_fn=save_history, session_fn=lambda: create_tls_session(impersonate="primevideo"))
            new_status = out.get('status', 'ERROR')
        else:
            return {"error": f"Unsupported service type: {rec_type}", "id": rec_id}
    except Exception as e:
        new_status = "ERROR"
        out = {"error": str(e)}
    finally:
        _recheck_mode.active = False

    status_upper = new_status.upper()
    if status_upper in ("LIVE", "PREMIUM", "ACTIVE"):
        final_status = "LIVE"
    elif status_upper in ("DEAD", "EXPIRED", "INVALID", "ERROR"):
        final_status = "DEAD"
    elif status_upper == "HOLD":
        final_status = "HOLD"
    else:
        final_status = new_status.upper()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    queue_db_write("update_history_status", {
        "id": rec_id,
        "status": final_status,
        "created_at": now
    })

    return {"id": rec_id, "old_status": old_status, "new_status": final_status, "type": rec_type, "detail": out}
