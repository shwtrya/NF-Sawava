import logging
import random
import requests
import sys

# ── TLS Fingerprint Spoofing (curl_cffi with requests fallback) ─────────────
try:
    if r'C:\Python314\Lib\site-packages' not in sys.path:
        sys.path.append(r'C:\Python314\Lib\site-packages')
    from curl_cffi import requests as curl_requests
    from curl_cffi.requests import errors as curl_errors
    CURL_CFFI_AVAILABLE = True
except Exception as e:
    curl_requests = None
    curl_errors = None
    CURL_CFFI_AVAILABLE = False
    logging.warning(f"curl_cffi not available: {e}. Falling back to standard requests.")

MODERN_TLS_PROFILES = [
    "chrome131",
    "chrome124",
    "chrome120",
    "safari18_0",
    "safari17_0",
    "edge101",
]

def get_recommended_impersonate(target_service=None):
    """Select the most optimal TLS browser fingerprint profile for the target service."""
    if target_service in ("disney", "netflix_token"):
        return random.choice(["safari18_0", "safari17_0"])
    elif target_service in ("openai", "chatgpt"):
        return random.choice(["chrome131", "chrome124"])
    elif target_service in ("primevideo", "amazon"):
        return random.choice(["chrome131", "chrome124", "edge101"])
    elif target_service in ("spotify", "crunchyroll"):
        return random.choice(["chrome131", "chrome120", "safari18_0"])
    return random.choice(MODERN_TLS_PROFILES)

def _map_curl_error(ex):
    """Translate curl_cffi errors to standard requests.exceptions so existing handlers work cleanly."""
    if not ex:
        return requests.exceptions.RequestException(str(ex))
    msg = str(ex).lower()
    if 'timeout' in msg or 'timed out' in msg:
        return requests.exceptions.Timeout(str(ex))
    elif 'proxy' in msg:
        return requests.exceptions.ProxyError(str(ex))
    elif 'connect' in msg or 'connection' in msg:
        return requests.exceptions.ConnectionError(str(ex))
    return requests.exceptions.RequestException(str(ex))

class TLSSessionWrapper:
    """Wrapper around curl_cffi.requests.Session or requests.Session for 100% API compatibility."""
    def __init__(self, raw_session, is_curl=True, impersonate="chrome131"):
        self._s = raw_session
        self.is_curl = is_curl
        self.impersonate = impersonate

    def mount(self, prefix, adapter):
        if hasattr(self._s, 'mount'):
            self._s.mount(prefix, adapter)

    def request(self, method, url, **kwargs):
        if self.is_curl:
            try:
                fn = getattr(self._s, method.lower())
                return fn(url, **kwargs)
            except Exception as ex:
                if curl_errors and isinstance(ex, (curl_errors.RequestsError, curl_errors.CurlError)):
                    raise _map_curl_error(ex) from ex
                raise
        return self._s.request(method, url, **kwargs)

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def put(self, url, **kwargs):
        return self.request('PUT', url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request('DELETE', url, **kwargs)

    def head(self, url, **kwargs):
        return self.request('HEAD', url, **kwargs)

    def options(self, url, **kwargs):
        return self.request('OPTIONS', url, **kwargs)

    def __getattr__(self, name):
        return getattr(self._s, name)

def create_tls_session(impersonate="chrome131", proxies=None, timeout=15):
    """
    Returns an HTTP Session with browser TLS/JA3/JA4 fingerprint impersonation.
    Supports randomized rotation, Chrome 131/124, Safari 18, Edge 101, etc.
    """
    if impersonate == "random" or impersonate in ("auto", None):
        target_imp = get_recommended_impersonate()
    elif impersonate in ("disney", "openai", "primevideo", "spotify", "crunchyroll", "netflix_token"):
        target_imp = get_recommended_impersonate(impersonate)
    else:
        target_imp = impersonate

    if CURL_CFFI_AVAILABLE and curl_requests is not None:
        try:
            s = curl_requests.Session(impersonate=target_imp)
            if proxies:
                s.proxies = proxies
            return TLSSessionWrapper(s, is_curl=True, impersonate=target_imp)
        except Exception as ex:
            logging.debug(f"Failed to create curl_cffi session with {target_imp}: {ex}")

    s = requests.Session()
    if proxies:
        s.proxies = proxies
    return TLSSessionWrapper(s, is_curl=False, impersonate="requests_fallback")

def tls_request(method, url, impersonate="chrome131", **kwargs):
    """Execute an HTTP request with browser TLS fingerprinting."""
    if impersonate == "random" or impersonate in ("auto", None):
        target_imp = get_recommended_impersonate()
    elif impersonate in ("disney", "openai", "primevideo", "spotify", "crunchyroll", "netflix_token"):
        target_imp = get_recommended_impersonate(impersonate)
    else:
        target_imp = impersonate

    if CURL_CFFI_AVAILABLE and curl_requests is not None:
        try:
            func = getattr(curl_requests, method.lower(), curl_requests.get)
            return func(url, impersonate=target_imp, **kwargs)
        except Exception as ex:
            if curl_errors and isinstance(ex, (curl_errors.RequestsError, curl_errors.CurlError)):
                raise _map_curl_error(ex) from ex
            logging.debug(f"curl_cffi {method} failed, falling back to requests: {ex}")

    kwargs.pop("impersonate", None)
    func = getattr(requests, method.lower(), requests.get)
    return func(url, **kwargs)
