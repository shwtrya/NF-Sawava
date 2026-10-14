"""
PrimeVideo Cookie Checker for NF-Sawava Suite
Validates Amazon Prime Video session cookies and detects subscription status.
"""

import json
import re
import logging
import traceback
import requests

REQUEST_HEADERS = {
    "Host": "www.primevideo.com",
    "Connection": "keep-alive",
    "device-memory": "4",
    "sec-ch-device-memory": "4",
    "dpr": "1",
    "sec-ch-dpr": "1",
    "viewport-width": "1366",
    "sec-ch-viewport-width": "1366",
    "rtt": "100",
    "downlink": "2.7",
    "ect": "4g",
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-ch-ua-platform-version": '"19.0.0"',
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-User": "?1",
    "Sec-Fetch-Dest": "document",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
}

CONFIG_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}

REQUIRED_AUTH_COOKIE_KEYS = ("session-token",)

# Accept both standard and regional/variant cookie names
# e.g. ubid-main, ubid-main-av, at-main, at-main-av, x-main, x-main-av
AUTH_COOKIE_PREFIXES = ("session-token", "ubid-main", "at-main", "x-main", "sess-at-main")

STOREFRONT_URL = "https://www.primevideo.com/storefront"
CONFIG_URL = "https://atv-ps.primevideo.com/cdp/catalog/GetPlaybackResources"
PROFILE_URL = "https://www.primevideo.com/gp/video/api/getProfiles"


def parse_primevideo_cookies(raw_text):
    """Parse cookies from JSON array, Netscape format, key=value, or raw header string.
    Also handles '$'-delimited multi-account format (returns cookies for first/current block only).
    Supports regional cookie suffixes like -av, -acbid, etc.
    """
    if str(raw_text).strip().startswith("enc:"):
        try:
            from modules.db import decrypt_credential
            raw_text = decrypt_credential(raw_text).strip()
        except Exception:
            pass
    cookies = {}
    text = raw_text.strip()

    # 0. Handle '$' delimiter — split and take only first block (one account)
    if '$' in text:
        blocks = [b.strip() for b in text.split('$') if b.strip()]
        if blocks:
            text = blocks[0]

    # 1. JSON array: [{"name":"session-token","value":"xxx",...}]
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict) and "cookies" in data:
                data = data["cookies"]
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                        value = item.get("value", "")
                        if name and value:
                            cookies[name] = value
                if cookies:
                    return cookies
        except json.JSONDecodeError:
            pass

    # 2. Netscape tab-separated format
    lines = text.split("\n")
    netscape_count = 0
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            name = parts[5].strip()
            value = parts[6].strip()
            if name and value:
                cookies[name] = value
                netscape_count += 1
    if netscape_count > 0:
        return cookies

    # 3. Key=value pairs (cookie header or semicolon-separated)
    # Try semicolon-separated first
    if ";" in text and "=" in text:
        for pair in text.split(";"):
            pair = pair.strip()
            if "=" in pair:
                idx = pair.index("=")
                name = pair[:idx].strip()
                value = pair[idx + 1:].strip()
                if name and value:
                    cookies[name] = value
        if cookies:
            return cookies

    # 4. Line-by-line key=value
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            idx = line.index("=")
            name = line[:idx].strip()
            value = line[idx + 1:].strip()
            if name and value:
                cookies[name] = value

    return cookies


def check_primevideo_cookie(cookie_text, use_proxy=True, get_proxy_fn=None, cooldown_fn=None, save_fn=None, session_fn=None):
    """
    Check a Prime Video cookie.
    Returns dict with: status, plan, profile, region, customer_id, route, reason
    """
    result = {
        "status": "ERROR",
        "plan": "Unknown",
        "profile": "",
        "region": "",
        "customer_id": "",
        "route": "Direct",
        "reason": "",
    }

    try:
        cookies = parse_primevideo_cookies(cookie_text)
        if not cookies:
            result["status"] = "DEAD"
            result["reason"] = "Tidak bisa parse cookie"
            if save_fn:
                save_fn("primevideo", "DEAD", raw_cookie=cookie_text)
            return result

        # Check minimum required cookies — accept regional suffixes (-av, -acbid, etc.)
        has_session = any(k.startswith("session-token") for k in cookies)
        has_auth = has_session and any(
            any(k.startswith(prefix) for prefix in AUTH_COOKIE_PREFIXES if prefix != "session-token")
            for k in cookies
        )
        if not has_session:
            result["status"] = "DEAD"
            result["reason"] = "Cookie 'session-token' tidak ditemukan"
            if save_fn:
                save_fn("primevideo", "DEAD", raw_cookie=cookie_text)
            return result

        max_retries = 5 if use_proxy and get_proxy_fn else 1
        last_err = None

        for attempt in range(max_retries):
            proxies = None
            proxy_label = "Direct"
            proxy_url = None

            if use_proxy and get_proxy_fn:
                try:
                    proxies, proxy_label, proxy_url = get_proxy_fn()
                    if proxy_label:
                        result["route"] = proxy_label
                except Exception:
                    proxies = None

            try:
                sess = session_fn() if session_fn else requests.Session()
                sess.headers.update(REQUEST_HEADERS)
                sess.cookies.update(cookies)
                if proxies:
                    sess.proxies.update(proxies)

                # Step 1: GET storefront page
                resp = sess.get(
                    STOREFRONT_URL,
                    timeout=20,
                    allow_redirects=True
                )

                final_url = resp.url
                page_text = resp.text

                # Check if redirected to sign-in → dead cookie
                if "signin" in final_url.lower() or "/ap/signin" in final_url or \
                   "nonprimehomepage" in final_url.lower() or "_ssoLoop" in final_url or \
                   "/offers/" in final_url:
                    result["status"] = "DEAD"
                    result["reason"] = "Cookie expired (redirected to sign-in/offers page)"
                    if save_fn:
                        save_fn("primevideo", "DEAD", raw_cookie=cookie_text, route=result["route"])
                    return result

                if resp.status_code == 503:
                    result["status"] = "DEAD"
                    result["reason"] = "Service unavailable (503) - possible bot detection"
                    if cooldown_fn and proxy_url:
                        cooldown_fn(proxy_url, 60)
                    last_err = result["reason"]
                    continue

                if resp.status_code != 200:
                    last_err = f"HTTP {resp.status_code}"
                    if cooldown_fn and proxy_url:
                        cooldown_fn(proxy_url, 30)
                    continue

                # Step 2: Extract profile name from HTML
                # Look for profile/user info in page
                profile_match = re.search(r'"displayName"\s*:\s*"([^"]+)"', page_text)
                if not profile_match:
                    profile_match = re.search(r'data-testid="active-profile-[^"]*"[^>]*>([^<]+)', page_text)
                if not profile_match:
                    profile_match = re.search(r'"name"\s*:\s*"([^"]+)".*?"isSelected"\s*:\s*true', page_text, re.DOTALL)
                if not profile_match:
                    profile_match = re.search(r'"profileName"\s*:\s*"([^"]+)"', page_text)

                if profile_match:
                    result["profile"] = profile_match.group(1)

                # Step 3: Extract customer ID and territory from page state/config
                cid_match = re.search(r'"customerId"\s*:\s*"([^"]+)"', page_text)
                if not cid_match:
                    cid_match = re.search(r'"customerID"\s*:\s*"([^"]+)"', page_text)
                if not cid_match:
                    cid_match = re.search(r'"directedId"\s*:\s*"([^"]+)"', page_text)
                if cid_match:
                    result["customer_id"] = cid_match.group(1)

                territory_match = re.search(r'"currentTerritory"\s*:\s*"([^"]+)"', page_text)
                if not territory_match:
                    territory_match = re.search(r'"recordTerritory"\s*:\s*"([^"]+)"', page_text)
                if not territory_match:
                    territory_match = re.search(r'"marketplace(?:Id)?"\s*:\s*"([^"]+)"', page_text)
                if not territory_match:
                    territory_match = re.search(r'"territory"\s*:\s*"([^"]+)"', page_text)
                if territory_match:
                    result["region"] = territory_match.group(1)

                # Step 4: Determine subscription status
                # Check for Prime indicators in page content
                is_prime_paid = False
                is_free = False

                # Method A: watchlistAction pattern
                watchlist_match = re.search(r'"watchlistAction"\s*:\s*\{[^}]*"ajaxEnabled"\s*:\s*(true|false)', page_text)
                if watchlist_match:
                    if watchlist_match.group(1) == "true":
                        is_prime_paid = True
                    else:
                        is_free = True

                # Method B: subscription/entitlement data in page
                if not is_prime_paid and not is_free:
                    if re.search(r'"planType"\s*:\s*"(?:PRIME|prime|PREMIUM|premium)"', page_text):
                        is_prime_paid = True
                    elif re.search(r'"isPrimeMember"\s*:\s*true', page_text, re.IGNORECASE):
                        is_prime_paid = True
                    elif re.search(r'"hasPrimeBenefit"\s*:\s*true', page_text, re.IGNORECASE):
                        is_prime_paid = True
                    elif re.search(r'"PRIME_SUBSCRIPTION_BENEFIT"', page_text):
                        is_prime_paid = True

                # Method C: Try getProfiles API for more data
                if not is_prime_paid and not is_free:
                    try:
                        profile_resp = sess.get(
                            PROFILE_URL,
                            headers={
                                "Accept": "application/json",
                                "User-Agent": REQUEST_HEADERS["User-Agent"],
                            },
                            timeout=15,
                        )
                        if profile_resp.status_code == 200:
                            pdata = profile_resp.json()
                            profiles = pdata if isinstance(pdata, list) else pdata.get("profiles", [])
                            if profiles:
                                if not result["profile"]:
                                    for p in profiles:
                                        if p.get("isDefault") or p.get("isSelected"):
                                            result["profile"] = p.get("name", p.get("profileName", ""))
                                            break
                                    if not result["profile"] and profiles:
                                        result["profile"] = profiles[0].get("name", profiles[0].get("profileName", ""))
                    except Exception:
                        pass

                # Method D: Check page for "freetime" vs subscription content indicators
                if not is_prime_paid and not is_free:
                    if re.search(r'class="[^"]*(?:pv-subscribe|subscribe-button|start-your-free-trial)', page_text):
                        is_free = True
                    elif result["customer_id"]:
                        # Has customer ID = at least logged in, assume some access
                        is_prime_paid = True

                # Determine final status
                if not result["customer_id"] and not result["profile"]:
                    # No customer data found, might be logged out even though no redirect
                    # Check for any auth indicator
                    if re.search(r'"isLoggedIn"\s*:\s*false', page_text) or \
                       re.search(r'"isAuthenticated"\s*:\s*false', page_text):
                        result["status"] = "DEAD"
                        result["reason"] = "Not authenticated"
                        if save_fn:
                            save_fn("primevideo", "DEAD", raw_cookie=cookie_text, route=result["route"])
                        return result

                if is_prime_paid:
                    result["status"] = "LIVE"
                    result["plan"] = "Prime"
                    result["reason"] = "Active Prime subscription"
                elif is_free:
                    result["status"] = "FREE"
                    result["plan"] = "Free"
                    result["reason"] = "Free tier (no Prime subscription)"
                else:
                    # Logged in but can't determine plan
                    if result["customer_id"] or result["profile"]:
                        result["status"] = "LIVE"
                        result["plan"] = "Unknown"
                        result["reason"] = "Authenticated (plan detection unclear)"
                    else:
                        result["status"] = "DEAD"
                        result["reason"] = "Unable to verify authentication"
                        if save_fn:
                            save_fn("primevideo", "DEAD", raw_cookie=cookie_text, route=result["route"])
                        return result

                if save_fn:
                    save_fn("primevideo", result["status"],
                            plan=result["plan"],
                            country=result["region"],
                            route=result["route"],
                            raw_cookie=cookie_text)
                return result

            except requests.exceptions.Timeout:
                last_err = "Request timeout"
                if cooldown_fn and proxy_url:
                    cooldown_fn(proxy_url, 30)
                continue
            except requests.exceptions.ProxyError:
                last_err = "Proxy error"
                if cooldown_fn and proxy_url:
                    cooldown_fn(proxy_url, 120)
                continue
            except requests.exceptions.ConnectionError:
                last_err = "Connection error"
                if cooldown_fn and proxy_url:
                    cooldown_fn(proxy_url, 60)
                continue
            except Exception as e:
                last_err = str(e)
                logging.warning(f"PrimeVideo check attempt {attempt + 1} error: {e}")
                continue

        # All retries exhausted
        result["status"] = "ERROR"
        result["reason"] = f"All {max_retries} attempts failed: {last_err}"
        return result

    except Exception as e:
        logging.error(f"PrimeVideo checker fatal error: {traceback.format_exc()}")
        result["status"] = "ERROR"
        result["reason"] = str(e)
        return result
