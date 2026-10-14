"""
Backward-compatibility forwarder for primevideo_checker.
Implementation moved to checkers.primevideo.
"""
from checkers.primevideo import *
from checkers.primevideo import (
    check_primevideo_cookie,
    parse_primevideo_cookies,
    REQUIRED_AUTH_COOKIE_KEYS
)
