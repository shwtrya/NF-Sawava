import json
import re
import urllib.parse
from modules.config import COOKIE_KEYS

def extract_cookie_values(text):
    """Extract standard cookie values (e.g. Netflix) from text in Netscape, JSON, or key=value formats."""
    cookie_dict = {}
    if not text:
        return cookie_dict

    text = str(text).strip()

    json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]', text)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if isinstance(parsed, list):
                for c in parsed:
                    if isinstance(c, dict):
                        n, v = c.get("name"), c.get("value")
                        if n in COOKIE_KEYS and isinstance(v, str):
                            cookie_dict[n] = urllib.parse.unquote(v) if "%" in v else v
        except Exception:
            pass

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("═") or line.startswith("█") or line.startswith("–"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookie_dict[parts[5]] = parts[6]

    try:
        data = json.loads(text)
    except Exception:
        data = None

    if isinstance(data, list):
        for c in data:
            if isinstance(c, dict):
                n, v = c.get("name"), c.get("value")
                if n in COOKIE_KEYS and isinstance(v, str):
                    cookie_dict[n] = urllib.parse.unquote(v) if "%" in v else v
    elif isinstance(data, dict):
        for k in COOKIE_KEYS:
            v = data.get(k)
            if isinstance(v, str):
                cookie_dict[k] = urllib.parse.unquote(v) if "%" in v else v

    for k in COOKIE_KEYS:
        if k not in cookie_dict:
            m = re.search(rf"(?:•\s*Cookie:\s*|[;\s]|^){re.escape(k)}=([^;,\r\n\s]+)", text)
            if m:
                v = m.group(1)
                cookie_dict[k] = urllib.parse.unquote(v) if "%" in v else v

    for k in list(cookie_dict.keys()):
        if isinstance(cookie_dict[k], str):
            cookie_dict[k] = cookie_dict[k].strip().rstrip('.')

    return cookie_dict

def get_cookie_fingerprint(text):
    """Generates a stable identifier/fingerprint for cookie deduplication."""
    if not text:
        return ""
    ck = extract_cookie_values(text)
    nid = ck.get("NetflixId", "")
    if nid:
        ct_m = re.search(r'ct=([^&]+)', nid)
        if ct_m:
            return f"ct:{ct_m.group(1)}"
        return f"nid:{nid.strip()}"
    cleaned = re.sub(r'\s+', '', str(text).strip())
    return f"raw:{cleaned[:120]}"

def detect_universal_format(text):
    """
    Zero-config universal detector for pasted account/cookie data.
    Identifies target service, data format, item count, and normalized items.
    """
    if not text or not str(text).strip():
        return {
            "service": "none",
            "format": "empty",
            "count": 0,
            "items": [],
            "label": "Belum ada input",
            "hint": "Paste cookies atau combo akun di sini"
        }
    t = str(text).strip()

    # 1. JSON Array (Cookie-Editor / EditThisCookie)
    if (t.startswith('[') and t.endswith(']')) or re.search(r'\[\s*\{[\s\S]*?\}\s*\]', t):
        svc = "unknown"
        if "NetflixId" in t or "netflix.com" in t: svc = "netflix"
        elif "sp_dc" in t or "spotify.com" in t: svc = "spotify"
        elif "__Secure-next-auth" in t or "chatgpt" in t or "openai" in t: svc = "openai"
        elif "session-token" in t or "ubid-main" in t or "amazon" in t: svc = "primevideo"
        elif "etp_rt" in t or "crunchyroll" in t: svc = "crunchyroll"
        elif "disney" in t or "bamgrid" in t: svc = "disney"

        lines = [l.strip() for l in t.splitlines() if l.strip()]
        json_lines = [l for l in lines if l.startswith('[') and l.endswith(']')]
        cnt = len(json_lines) if len(json_lines) > 1 else 1
        items = json_lines if len(json_lines) > 1 else [t]
        return {
            "service": svc,
            "format": "json_cookies",
            "count": cnt,
            "items": items,
            "label": f"JSON Cookie Array ({cnt} set)",
            "hint": f"Format JSON terverifikasi untuk {svc.upper() if svc != 'unknown' else 'Cookie'}"
        }

    # 2. Netscape HTTP Cookie File (.txt)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    netscape_lines = [l for l in lines if l.count('\t') >= 5 and not l.startswith('#')]
    if netscape_lines or "# Netscape HTTP Cookie File" in t:
        svc = "unknown"
        if ".netflix.com" in t or "NetflixId" in t: svc = "netflix"
        elif ".spotify.com" in t or "sp_dc" in t: svc = "spotify"
        elif "chatgpt.com" in t or "openai.com" in t: svc = "openai"
        elif "crunchyroll.com" in t or "etp_rt" in t: svc = "crunchyroll"
        elif "primevideo.com" in t or "amazon.com" in t: svc = "primevideo"
        elif "disney" in t or "bamgrid" in t: svc = "disney"

        blocks = re.split(r'(?=# Netscape|\n\s*\n|# =+)', t)
        valid_blocks = [b.strip() for b in blocks if any(l.count('\t') >= 5 for l in b.splitlines())]
        cnt = max(1, len(valid_blocks))
        return {
            "service": svc,
            "format": "netscape",
            "count": cnt,
            "items": valid_blocks if valid_blocks else [t],
            "label": f"Netscape Cookie File ({cnt} set/akun)",
            "hint": f"Format Netscape terverifikasi untuk {svc.upper() if svc != 'unknown' else 'Cookie'}"
        }

    # 3. Credential Combo (email:pass)
    combo_lines = [l for l in lines if re.match(r'^[^\s:;|,]+@[^\s:;|,]+\.[^\s:;|,]+[:|;,\t].+$', l)]
    if combo_lines and len(combo_lines) >= len(lines) * 0.4:
        svc = "combo"
        if "crunchyroll" in t.lower():
            svc = "crunchyroll"
        elif "disney" in t.lower():
            svc = "disney"
        elif "expressvpn" in t.lower():
            svc = "expressvpn"
        elif any(re.search(r'@(?:outlook|hotmail|live|msn)\.', l, re.I) for l in combo_lines):
            svc = "outlook"
        return {
            "service": svc,
            "format": "combo",
            "count": len(combo_lines),
            "items": combo_lines,
            "label": f"Combo Email:Pass ({len(combo_lines)} akun)",
            "hint": f"Format combo terverifikasi untuk {svc.upper() if svc != 'combo' else 'Multi-Service'}"
        }

    # 4. Raw Header / Key=Value
    if re.search(r'(?:NetflixId|sp_dc|session-token|__Secure-next-auth|etp_rt)=', t):
        svc = "unknown"
        if "NetflixId=" in t: svc = "netflix"
        elif "sp_dc=" in t: svc = "spotify"
        elif "__Secure-next-auth" in t: svc = "openai"
        elif "session-token=" in t: svc = "primevideo"
        elif "etp_rt=" in t: svc = "crunchyroll"
        return {
            "service": svc,
            "format": "header_cookie",
            "count": 1,
            "items": [t],
            "label": f"Header Cookie ({svc.upper() if svc != 'unknown' else 'Key=Value'})",
            "hint": "Format string cookie key=value standar"
        }

    # 5. Raw Single Token
    if len(t) > 30 and ' ' not in t and '\n' not in t:
        if t.startswith("AQB") or len(t) in range(80, 260):
            return {
                "service": "spotify",
                "format": "raw_token",
                "count": 1,
                "items": [t],
                "label": "Raw Token (Spotify sp_dc)",
                "hint": "Token sp_dc Spotify mandiri terdeteksi"
            }
        elif t.startswith("ey"):
            return {
                "service": "openai",
                "format": "raw_token",
                "count": 1,
                "items": [t],
                "label": "Raw JWT Token (OpenAI Session)",
                "hint": "Session JWT OpenAI terdeteksi"
            }

    # 6. Fallback
    return {
        "service": "unknown",
        "format": "plain_text",
        "count": len(lines),
        "items": lines,
        "label": f"Teks Bebas ({len(lines)} baris)",
        "hint": "Format tidak dikenal, akan diproses apa adanya"
    }
