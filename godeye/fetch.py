"""Shared HTTP client. curl_cffi impersonates Chrome's TLS fingerprint, which Shopify/Cloudflare
require — plain requests/urllib get 429 or a challenge page."""
from curl_cffi import requests

_session = None


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def session():
    global _session
    if _session is None:
        _session = requests.Session(impersonate="chrome")
    return _session


def get(url: str, params: dict | None = None, timeout: int = 25):
    try:
        r = session().get(url, params=params, timeout=timeout)
    except Exception as e:  # network errors, DNS, timeouts
        raise FetchError(f"Network error: {e.__class__.__name__}") from e
    if r.status_code == 429:
        raise FetchError("Rate limited by site (429) — backing off", 429)
    if "Just a moment..." in r.text[:2000]:
        raise FetchError("Blocked by Cloudflare challenge", 403)
    if r.status_code >= 400:
        raise FetchError(f"HTTP {r.status_code}", r.status_code)
    return r


def get_json(url: str, params: dict | None = None):
    r = get(url, params=params)
    try:
        return r.json()
    except ValueError as e:
        raise FetchError("Site returned something that isn't JSON") from e
