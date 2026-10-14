import datetime
import json
import logging
import re
import requests
from modules.db import save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown
from modules.tls_engine import create_tls_session

OPENAI_SESSION_TOKEN_NAMES = ("__Secure-next-auth.session-token",)
OPENAI_RELATED_COOKIE_NAMES = (
    "__Secure-next-auth.callback-url", "__Host-next-auth-csrf-token",
    "_cfuvid", "cf_clearance", "__cf_bm", "oai-did", "oai-sc",
    "oai-dm-tgt-c-240329",
    "__Secure-next-auth.session-token.0",
    "__Secure-next-auth.session-token.1",
)

def extract_openai_session_token(cookie_text):
    """Parse __Secure-next-auth.session-token from JSON array, Netscape .txt, key=value, or raw token."""
    if not cookie_text or not isinstance(cookie_text, str):
        return None, {}
    cookie_text = cookie_text.strip()
    other_cookies = {}
    session_token = None

    try:
        data = json.loads(cookie_text)
        if isinstance(data, list):
            for item in data:
                name = item.get("name", "") or item.get("Name", "")
                value = item.get("value", "") or item.get("Value", "")
                domain = item.get("domain", "") or item.get("Domain", "")
                if name == "__Secure-next-auth.session-token":
                    session_token = value
                elif name and value and ("openai.com" in domain or "chatgpt.com" in domain):
                    other_cookies[name] = value
            if session_token:
                return session_token, other_cookies
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

    lines = cookie_text.splitlines()
    netscape_found = False
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            netscape_found = True
            name = parts[5]
            value = parts[6]
            if name == "__Secure-next-auth.session-token":
                session_token = value
            elif "openai.com" in parts[0] or "chatgpt.com" in parts[0]:
                other_cookies[name] = value
    if netscape_found and session_token:
        return session_token, other_cookies

    kv_pattern = re.compile(r'([^=;\s]+)\s*=\s*([^;\n]+)')
    pairs = kv_pattern.findall(cookie_text)
    if pairs:
        for name, value in pairs:
            name = name.strip()
            value = value.strip()
            if name == "__Secure-next-auth.session-token":
                session_token = value
            elif name in OPENAI_RELATED_COOKIE_NAMES:
                other_cookies[name] = value
        if session_token:
            return session_token, other_cookies

    raw = cookie_text.strip().strip('"').strip("'")
    if len(raw) > 40 and "\t" not in raw and ";" not in raw and "=" not in raw and " " not in raw:
        return raw, {}

    if not session_token and other_cookies:
        t0 = other_cookies.pop("__Secure-next-auth.session-token.0", "")
        t1 = other_cookies.pop("__Secure-next-auth.session-token.1", "")
        if t0:
            session_token = t0 + t1
            return session_token, other_cookies

    return None, {}

def check_openai_cookie(cookie_text, use_proxy=True):
    """Check an OpenAI/ChatGPT account using session cookies."""
    result = {
        "status": "ERROR",
        "email": "",
        "plan": "",
        "subscription_plan": "",
        "is_paid": False,
        "route": "Direct",
        "reason": ""
    }
    proxy_raw_url = None

    try:
        session_token, extra_cookies = extract_openai_session_token(cookie_text)
        if not session_token:
            result["status"] = "DEAD"
            result["reason"] = "Session token (__Secure-next-auth.session-token) tidak ditemukan."
            save_history("openai", "DEAD", raw_cookie=cookie_text)
            return result

        cookies = {"__Secure-next-auth.session-token": session_token}
        cookies.update(extra_cookies)

        headers_base = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
            "Accept": "application/json",
        }

        session = create_tls_session(impersonate="chrome131")
        session.verify = False
        proxies = None
        proxy_label = "Direct"

        if use_proxy:
            proxies, proxy_label, proxy_raw_url = get_random_proxy()
            if proxies:
                session.proxies = proxies
                result["route"] = f"Proxy ({proxy_label})"

        def do_request(attempt_direct_fallback=True):
            nonlocal proxy_raw_url

            try:
                resp_auth = session.get(
                    "https://chatgpt.com/api/auth/session",
                    headers=headers_base,
                    cookies=cookies,
                    timeout=30
                )

                if resp_auth.status_code in (403, 429):
                    if proxy_raw_url:
                        mark_proxy_cooldown(proxy_raw_url, 600)
                    if attempt_direct_fallback and use_proxy:
                        session.proxies = {}
                        result["route"] = "Direct"
                        proxy_raw_url = None
                        return do_request(attempt_direct_fallback=False)
                    result["status"] = "DEAD"
                    result["reason"] = f"Auth session returned {resp_auth.status_code}"
                    return result

                if resp_auth.status_code != 200:
                    result["status"] = "DEAD"
                    result["reason"] = f"Auth session HTTP {resp_auth.status_code}"
                    return result

                try:
                    auth_data = resp_auth.json()
                except (json.JSONDecodeError, ValueError):
                    result["status"] = "DEAD"
                    result["reason"] = "Auth session returned invalid JSON"
                    return result

                if not auth_data or (isinstance(auth_data, dict) and not auth_data.get("accessToken") and not auth_data.get("access_token") and not auth_data.get("user")):
                    result["status"] = "DEAD"
                    result["reason"] = "Cookie expired (empty session response)"
                    return result

                access_token = auth_data.get("accessToken") or auth_data.get("access_token", "")
                user_info = auth_data.get("user", {})
                email = user_info.get("email", "") if isinstance(user_info, dict) else ""

                if not access_token:
                    result["status"] = "DEAD"
                    result["email"] = email
                    result["reason"] = "Cookie expired / No access token."
                    return result

                result["email"] = email

                headers_check = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                    "OAI-Language": "en-US",
                    "Referer": "https://chatgpt.com/",
                }

                resp_check = session.get(
                    "https://chatgpt.com/backend-api/accounts/check/v4-2023-04-27?timezone_offset_min=420",
                    headers=headers_check,
                    cookies=cookies,
                    timeout=30
                )

                if resp_check.status_code in (403, 429):
                    if proxy_raw_url:
                        mark_proxy_cooldown(proxy_raw_url, 600)
                    if attempt_direct_fallback and use_proxy:
                        session.proxies = {}
                        result["route"] = "Direct"
                        proxy_raw_url = None
                        return do_request(attempt_direct_fallback=False)

                if resp_check.status_code == 401:
                    result["status"] = "DEAD"
                    result["email"] = email
                    result["reason"] = "Token revoked / invalidated"
                    try:
                        err_data = resp_check.json()
                        err_msg = err_data.get("error", {}).get("message", "")
                        err_code = err_data.get("error", {}).get("code", "")
                        if err_msg:
                            result["reason"] = f"{err_code}: {err_msg}" if err_code else err_msg
                    except Exception:
                        pass
                    return result

                subscription_plan = ""
                plan_type = ""
                plan_display_name = ""
                has_plus = False
                is_paid = False

                if resp_check.status_code == 200:
                    try:
                        check_data = resp_check.json()
                    except (json.JSONDecodeError, ValueError):
                        check_data = {}

                    if isinstance(check_data, dict):
                        accounts = check_data.get("accounts", {})
                        if isinstance(accounts, dict):
                            for acc_key, acc_val in accounts.items():
                                if not isinstance(acc_val, dict):
                                    continue
                                acct = acc_val.get("account", {})
                                if isinstance(acct, dict):
                                    plan_type = plan_type or acct.get("plan_type", "")
                                    plan_display_name = plan_display_name or acct.get("plan_display_name", "")
                                    is_paid = is_paid or bool(acct.get("is_paid", False))
                                ent = acc_val.get("entitlement", {})
                                if isinstance(ent, dict):
                                    if not plan_type:
                                        subscription_plan = subscription_plan or ent.get("subscription_plan", "")
                                    has_plus = has_plus or bool(ent.get("has_active_subscription", False))

                    if not plan_type and not subscription_plan:
                        check_text = resp_check.text
                        pt_match = re.search(r'"plan_type"\s*:\s*"([^"]+)"', check_text)
                        if pt_match:
                            plan_type = pt_match.group(1)
                        else:
                            sp_match = re.search(r'"subscription_plan"\s*:\s*"([^"]+)"', check_text)
                            if sp_match:
                                subscription_plan = sp_match.group(1)

                auth_plan_type = ""
                auth_account = auth_data.get("account", {})
                if isinstance(auth_account, dict):
                    auth_plan_type = auth_account.get("planType", "")

                effective_plan = plan_type or auth_plan_type or ""
                result["subscription_plan"] = effective_plan or subscription_plan

                result["_debug"] = {
                    "auth_status": resp_auth.status_code,
                    "auth_keys": list(auth_data.keys()) if isinstance(auth_data, dict) else str(type(auth_data)),
                    "check_status": resp_check.status_code,
                    "subscription_plan": subscription_plan,
                    "plan_type": plan_type,
                    "has_plus": has_plus,
                    "is_paid": is_paid,
                    "check_body_preview": resp_check.text[:500] if resp_check.status_code == 200 else f"HTTP {resp_check.status_code}"
                }

                if resp_check.status_code != 200 and not subscription_plan:
                    if auth_plan_type:
                        ep_lower_fb = auth_plan_type.lower()
                        if ep_lower_fb == "free":
                            result["status"] = "FREE"
                            result["plan"] = "ChatGPT Free"
                            result["is_paid"] = False
                        else:
                            result["status"] = "LIVE"
                            result["plan"] = f"ChatGPT {auth_plan_type.title()}"
                            result["is_paid"] = True
                    else:
                        result["status"] = "FREE"
                        result["plan"] = "ChatGPT Free"
                        result["is_paid"] = False
                    return result

                ep_lower = effective_plan.lower().strip() if effective_plan else ""

                if ep_lower == "free":
                    result["status"] = "FREE"
                    result["plan"] = plan_display_name or "ChatGPT Free"
                    result["is_paid"] = False
                elif ep_lower == "plus":
                    result["status"] = "LIVE"
                    result["plan"] = plan_display_name or "ChatGPT Plus"
                    result["is_paid"] = True
                elif ep_lower == "pro":
                    result["status"] = "LIVE"
                    result["plan"] = plan_display_name or "ChatGPT Pro"
                    result["is_paid"] = True
                elif ep_lower == "team":
                    result["status"] = "LIVE"
                    result["plan"] = plan_display_name or "ChatGPT Team"
                    result["is_paid"] = True
                elif ep_lower == "enterprise":
                    result["status"] = "LIVE"
                    result["plan"] = plan_display_name or "ChatGPT Enterprise"
                    result["is_paid"] = True
                elif effective_plan:
                    result["status"] = "LIVE" if (is_paid or has_plus) else "FREE"
                    result["plan"] = plan_display_name or effective_plan
                    result["is_paid"] = is_paid or has_plus
                elif subscription_plan:
                    sp_lower = subscription_plan.lower()
                    if sp_lower == "chatgptfreeplan":
                        result["status"] = "FREE"
                        result["plan"] = "ChatGPT Free"
                        result["is_paid"] = False
                    elif "plus" in sp_lower:
                        result["status"] = "LIVE"
                        result["plan"] = "ChatGPT Plus"
                        result["is_paid"] = True
                    elif "pro" in sp_lower:
                        result["status"] = "LIVE"
                        result["plan"] = "ChatGPT Pro"
                        result["is_paid"] = True
                    elif "team" in sp_lower:
                        result["status"] = "LIVE"
                        result["plan"] = "ChatGPT Team"
                        result["is_paid"] = True
                    else:
                        result["status"] = "LIVE" if (is_paid or has_plus) else "FREE"
                        result["plan"] = subscription_plan
                        result["is_paid"] = is_paid or has_plus
                else:
                    if is_paid or has_plus:
                        result["status"] = "LIVE"
                        result["plan"] = "ChatGPT Paid"
                        result["is_paid"] = True
                    else:
                        result["status"] = "FREE"
                        result["plan"] = "ChatGPT Free"
                        result["is_paid"] = False

                return result

            except (requests.exceptions.ProxyError, requests.exceptions.ConnectTimeout,
                    requests.exceptions.ConnectionError) as e:
                if attempt_direct_fallback and use_proxy:
                    if proxy_raw_url:
                        mark_proxy_cooldown(proxy_raw_url, 600)
                    session.proxies = {}
                    result["route"] = "Direct"
                    proxy_raw_url = None
                    return do_request(attempt_direct_fallback=False)
                result["status"] = "ERROR"
                result["reason"] = f"Connection error: {str(e)[:120]}"
                return result

            except requests.exceptions.Timeout as e:
                if attempt_direct_fallback and use_proxy:
                    if proxy_raw_url:
                        mark_proxy_cooldown(proxy_raw_url, 600)
                    session.proxies = {}
                    result["route"] = "Direct"
                    proxy_raw_url = None
                    return do_request(attempt_direct_fallback=False)
                result["status"] = "ERROR"
                result["reason"] = f"Timeout: {str(e)[:120]}"
                return result

        result = do_request()

        save_history(
            "openai", result["status"],
            plan=result.get("plan", ""),
            country="",
            route=result["route"],
            raw_cookie=cookie_text,
            email=result.get("email", "")
        )

        return result

    except Exception as e:
        result["status"] = "ERROR"
        result["reason"] = f"Unhandled exception: {str(e)[:200]}"
        try:
            save_history("openai", "ERROR", route=result.get("route", "Direct"), raw_cookie=cookie_text, email="")
        except Exception:
            pass
        return result
