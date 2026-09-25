"""Signup, login, session state and the account panel data."""

import re
import secrets
import time

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, db, security
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


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=CONFIG["username_max"])
    password: str = Field(min_length=1, max_length=CONFIG["password_max"])


class Permanent(BaseModel):
    permanent: bool


@router.post("/api/signup")
def signup(body: Signup, response: Response):
    username = body.username.strip()
    if not USERNAME_RE.fullmatch(username):
        return JSONResponse(
            {"ok": False, "error": "username: letters, numbers, underscore only"},
            status_code=400,
        )

    conn = db.db()
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
    token = accounts.new_session(conn, cur.lastrowid)
    conn.close()

    accounts.set_session_cookie(response, token)
    return {"ok": True, "username": username, "account_number": number, "permanent": False}


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
        conn.commit()

    token = accounts.new_session(conn, user_id)
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
    ip = security.client_ip(request)
    conn = db.db()

    if user:
        msg_used = db.quota_used(conn, user["id"], None, "ct")
        img_used = db.quota_used(conn, user["id"], None, "image")
        msg_max, img_max = db.quota_limits(user["id"])
        conn.close()
        return {
            "ok": True,
            "logged_in": True,
            "username": user["username"],
            "account_number": user["account_number"],
            "permanent": bool(user["permanent"]),
            "quota": {"messages": [msg_used, msg_max], "images": [img_used, img_max]},
        }

    msg_used = db.quota_used(conn, None, ip, "ct")
    img_used = db.quota_used(conn, None, ip, "image")
    msg_max, img_max = db.quota_limits(None)
    conn.close()
    return {
        "ok": True,
        "logged_in": False,
        "quota": {"messages": [msg_used, msg_max], "images": [img_used, img_max]},
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
    description="accounts raise daily limits. account numbers rotate on login.",
)
