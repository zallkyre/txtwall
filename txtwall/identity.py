"""Who is placing a pixel.

The daily allowance has to survive a page reload, and it has to survive the
server restarting. That rules out anything kept in memory or in the
browser, so every visitor gets an identity the server issued itself:

* **Signed cookie.** A random device id plus an HMAC the client cannot
  forge or edit. Reloading keeps the same id. Clearing cookies loses the
  allowance, which is the one honest limitation of an anonymous system.
* **IP as the second lock.** The canvas checks both the cookie counter and
  an IP counter, so wiping cookies on the same connection does not buy a
  fresh allowance.
* **Accounts win outright.** A signed-in user is keyed by their user id,
  so they keep the same allowance across devices.

The HMAC secret is generated once and kept next to the database, so
restarting the app does not invalidate everyone.
"""

import hashlib
import hmac
import secrets

from fastapi import Request

from .config import DB_PATH

COOKIE = "tw_device"
SECRET_PATH = DB_PATH.parent / ".device_secret"


def _secret() -> bytes:
    """Load the signing secret, creating it on first run."""
    try:
        raw = SECRET_PATH.read_bytes().strip()
        if raw:
            return raw
    except OSError:
        pass
    raw = secrets.token_bytes(32)
    try:
        SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
        SECRET_PATH.write_bytes(raw)
    except OSError:
        pass  # fall through: a per-process secret still works, just resets identities
    return raw


def _sign(device_id: str) -> str:
    return hmac.new(_secret(), device_id.encode(), hashlib.sha256).hexdigest()[:32]


def new_device_id() -> str:
    return secrets.token_urlsafe(18)


def device_cookie_valid(value: str) -> str | None:
    """Return the device id if the cookie is well-formed and correctly signed."""
    if not value or "." not in value:
        return None
    device_id, _, signature = value.rpartition(".")
    if not device_id or not hmac.compare_digest(_sign(device_id), signature):
        return None
    return device_id


def ensure_device_cookie(request: Request, response) -> None:
    """Called from middleware: guarantees every visitor has an identity."""
    from .config import CONFIG

    if device_cookie_valid(request.cookies.get(COOKIE, "")):
        return
    device_id = new_device_id()
    response.set_cookie(
        COOKIE,
        f"{device_id}.{_sign(device_id)}",
        httponly=True,
        samesite="lax",
        max_age=CONFIG["device_cookie_days"] * 86400,
    )


def identity(request: Request, user) -> tuple:
    """The (key, user_id) pair that daily limits are tracked against.

    Accounts are keyed by user id so the allowance follows them between
    devices. Everyone else is keyed by their signed device cookie.
    """
    if user:
        return f"u:{user['id']}", user["id"]

    device_id = device_cookie_valid(request.cookies.get(COOKIE, ""))
    if not device_id:
        # Middleware normally guarantees this; if the cookie was stripped
        # mid-request fall back to the IP so the limit still holds.
        from .security import client_ip

        return f"ip:{client_ip(request)}", None
    return f"d:{device_id}", None


def hash_ip(ip: str) -> str:
    """Salted hash of an IP, for throttling without storing the address."""
    return hmac.new(_secret(), ip.encode(), hashlib.sha256).hexdigest()[:24]
