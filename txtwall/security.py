"""Rate limiting, client IP and response hardening.

The limiter is in-memory on purpose: this app runs as a single uvicorn
process on one Pi. If it ever runs behind more than one worker, move
`_hits` into redis or the database — the call sites do not change.
"""

import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import CONFIG

_hits = defaultdict(list)
_viewers = defaultdict(float)

VIEWER_WINDOW = 120  # seconds an IP counts as "here now"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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


# --- anonymous presence -----------------------------------------------------
def mark_viewer(ip: str) -> None:
    _viewers[ip] = time.time()
    if len(_viewers) > 5000:
        stale = [k for k, t in _viewers.items() if time.time() - t > VIEWER_WINDOW]
        for k in stale:
            del _viewers[k]


def viewer_count() -> int:
    now = time.time()
    return sum(1 for t in _viewers.values() if now - t < VIEWER_WINDOW)


async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp
