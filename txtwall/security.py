"""Rate limiting, client IP and response hardening.

The limiter is in-memory on purpose: this app runs as a single uvicorn
process on one Pi. If it ever runs behind more than one worker, move
`_hits` into redis or the database — the call sites do not change.

The important subtlety is `client_ip`. This app is bound to 127.0.0.1 and
reached through a Cloudflare Tunnel, so *every* request arrives from
loopback — ``request.client.host`` is the same value for all visitors.
Trusting it would give the entire internet one shared daily allowance and
one shared rate-limit bucket.

Cloudflare sets ``CF-Connecting-IP`` to the real visitor, and the tunnel
is the only thing that can reach the port, so that header is trustworthy
here. ``client_ip`` prefers it and says which source it used, so callers
can skip the "is this a private address" test for a header we already
trust.
"""

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import CONFIG

_hits = defaultdict(list)

# headers Cloudflare and ordinary reverse proxies set, in trust order
FORWARD_HEADERS = ("cf-connecting-ip", "x-real-ip", "x-forwarded-for")


def client_ip(request: Request) -> str:
    return client_ip_detail(request)[0]


def client_ip_detail(request: Request) -> tuple:
    """(ip, trusted). ``trusted`` means it came from a proxy header."""
    for header in FORWARD_HEADERS:
        raw = request.headers.get(header)
        if not raw:
            continue
        # x-forwarded-for can be a comma separated chain; the client is first
        candidate = raw.split(",")[0].strip()
        if candidate:
            return candidate, True

    return (request.client.host if request.client else "unknown"), False



def rate_limited(ip: str) -> bool:
    """True when this IP has used up its window. Counts the hit either way."""
    now = time.time()
    window = CONFIG["rate_window"]
    _hits[ip] = [t for t in _hits[ip] if now - t < window]
    if len(_hits[ip]) >= CONFIG["rate_limit"]:
        return True
    _hits[ip].append(now)
    if len(_hits) > 10000:  # keep the dict bounded
        _hits.clear()
    return False


def too_many() -> JSONResponse:
    return JSONResponse({"ok": False, "error": "slow down"}, status_code=429)


async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
