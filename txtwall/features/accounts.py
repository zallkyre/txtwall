"""Signup, login, session state and the allowance panel.

Signup is deliberately awkward, because a free account is worth 10x an
anonymous one and that is exactly the gap a bot would farm. Three things
stand in the way:

* **One account per IP per week**, so signing up again means waiting.
* **Turnstile**, a free Cloudflare challenge that humans pass and scripts
  mostly do not. This is the layer that actually does the work, and it is
  off until you paste in your keys.
* **A network check** for addresses that are never residential.

None of this is proof. It raises the cost of mass signup from trivial to
"some effort", which is the right bar for a site with one canvas on it.
"""

import json
import re
import secrets
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, db, geo, identity, security
from ..config import CONFIG
from . import feature

router = APIRouter()

USERNAME_RE = re.compile(r"[A-Za-z0-9_]+")


class Signup(BaseModel):
    username: str = Field(
        min_length=CONFIG["username_min"], max_length=CONFIG["username_max"]
    )
    password: str = Field(
        min_length=CONFIG["password_min"], max_length=CONFIG["password_max"]
    )
    turnstile_token: str = Field(default="", max_length=2048)


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=CONFIG["username_max"])
    password: str = Field(min_length=1, max_length=CONFIG["password_max"])


class Permanent(BaseModel):
    permanent: bool


def _verify_turnstile(token: str, ip: str) -> bool:
    """Check the challenge response. Returns True when it passes."""
    secret = CONFIG["turnstile_secret"]
    if not secret or not token:
        return False
    payload = urllib.parse.urlencode(
        {"secret": secret, "response": token, "remoteip": ip}
    ).encode()
    req = urllib.request.Request(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "txtwall/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return bool(json.loads(resp.read().decode()).get("success"))
    except Exception:
        return False


@router.post("/api/signup")
def signup(body: Signup, request: Request, response: Response):
    username = body.username.strip()
    if not USERNAME_RE.fullmatch(username):
        return JSONResponse(
            {"ok": False, "error": "username: letters, numbers, underscore only"},
            status_code=400,
        )

    ip = security.client_ip(request)
    ip_trusted = security.client_ip_detail(request)[1]
    if security.rate_limited(ip):
        return security.too_many()

    # --- gate 1: Turnstile ------------------------------------------
    if CONFIG["turnstile_required"] and not _verify_turnstile(body.turnstile_token, ip):
        return JSONResponse(
            {"ok": False, "error": "human check failed, reload and try again"},
            status_code=403,
        )

    # --- gate 2: is this a real person's network? --------------------
    allowed, reason = geo.check(ip, trusted=ip_trusted)
    if not allowed:
        return JSONResponse({"ok": False, "error": reason}, status_code=403)

    # --- gate 3: one account per IP per week -------------------------
    conn = db.db()
    ip_hash = identity.hash_ip(ip)
    week = db.week_start()
    row = conn.execute(
        "SELECT count FROM signup_limits WHERE ip_hash = ? AND week = ?", (ip_hash, week)
    ).fetchone()
    used = int(row[0]) if row else 0
    if used >= CONFIG["signup_per_week"]:
        retry_days = max(1, round((week + 7 * 86400 - int(time.time())) / 86400))
        conn.close()
        return JSONResponse(
            {
                "ok": False,
                "error": f"one account per week — try again in {retry_days} day(s)",
            },
            status_code=429,
        )

    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        return JSONResponse({"ok": False, "error": "username taken"}, status_code=409)

    salt = secrets.token_hex(16)
    number = accounts.unique_account_number(conn)
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, account_number, permanent, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (username, accounts.hash_password(body.password, salt), salt, number, int(time.time())),
    )
    conn.execute(
        "INSERT INTO signup_limits (ip_hash, week, count) VALUES (?, ?, 1) "
        "ON CONFLICT(ip_hash, week) DO UPDATE SET count = count + 1",
        (ip_hash, week),
    )
    token = accounts.new_session(conn, cur.lastrowid)
    conn.commit()
    conn.close()

    accounts.set_session_cookie(response, token)
    return {
        "ok": True,
        "username": username,
        "account_number": number,
        "daily_pixels": CONFIG["user_pixel_daily"],
    }


@router.post("/api/login")
def login(body: Login, response: Response):
    conn = db.db()
    row = conn.execute(
        "SELECT id, username, password_hash, salt, account_number, permanent "
        "FROM users WHERE username = ?",
        (body.username.strip(),),
    ).fetchone()
    if not row:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "wrong username or password"}, status_code=401
        )

    user_id, username, pw_hash, salt, number, permanent = row
    if accounts.hash_password(body.password, salt) != pw_hash:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": "wrong username or password"}, status_code=401
        )

    # rotate the account number on every login unless the user locked it
    if not permanent:
        number = accounts.unique_account_number(conn)
        conn.execute(
            "UPDATE users SET account_number = ? WHERE id = ?", (number, user_id)
        )

    conn.execute("UPDATE users SET last_active = ? WHERE id = ?", (int(time.time()), user_id))
    token = accounts.new_session(conn, user_id)
    conn.commit()
    conn.close()

    accounts.set_session_cookie(response, token)
    return {
        "ok": True,
        "username": username,
        "account_number": number,
        "permanent": bool(permanent),
    }


@router.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@router.get("/api/me")
def me(request: Request):
    user = accounts.current_user(request)
    ident, user_id = identity.identity(request, user)
    conn = db.db()

    allow = db.allowance(conn, user_id)
    used = db.used_today(conn, ident)
    state = {
        "used": used,
        "base": allow["base"],
        "credits": allow["credits"],
        "allowed": allow["allowed"],
        "left": max(0, allow["allowed"] - used),
        "cooldown": db.cooldown_left(conn, ident),
    }

    if not user:
        conn.close()
        return {"ok": True, "logged_in": False, "state": state}

    conn.close()
    return {
        "ok": True,
        "logged_in": True,
        "username": user["username"],
        "account_number": user["account_number"],
        "permanent": bool(user["permanent"]),
        "state": state,
    }


@router.post("/api/account/permanent")
def set_permanent(body: Permanent, request: Request):
    user = accounts.current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "not logged in"}, status_code=401)
    conn = db.db()
    conn.execute(
        "UPDATE users SET permanent = ? WHERE id = ?",
        (1 if body.permanent else 0, user["id"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "permanent": body.permanent}


feature(
    "accounts",
    router,
    title="Optional accounts",
    description="one account per week per IP. accounts raise the daily allowance to 100.",
)
