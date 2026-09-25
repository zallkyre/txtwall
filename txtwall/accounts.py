"""Accounts: passwords, rotating account numbers, sessions.

An account number is the public handle. It rotates on every login unless
the user locks it permanent, so the number cannot be used to track someone
across sessions. Deleting a message never touches the account itself.
"""

import hashlib
import secrets
import time

from fastapi import Request

from .config import CONFIG
from .db import db

PBKDF2_ROUNDS = 100_000


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), PBKDF2_ROUNDS
    ).hex()


def new_account_number() -> str:
    digits = CONFIG["account_number_digits"]
    # first digit never 0 so the number keeps its full length
    return str(secrets.randbelow(9) + 1) + "".join(
        str(secrets.randbelow(10)) for _ in range(digits - 1)
    )


def unique_account_number(conn) -> str:
    number = new_account_number()
    while conn.execute(
        "SELECT 1 FROM users WHERE account_number = ?", (number,)
    ).fetchone():
        number = new_account_number()
    return number


def new_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, int(time.time())),
    )
    conn.commit()
    return token


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        "session",
        token,
        httponly=True,
        samesite="lax",
        max_age=CONFIG["session_days"] * 86400,
    )


def current_user(request: Request):
    """The logged-in user for this request, or None."""
    token = request.cookies.get("session")
    if not token:
        return None
    conn = db()
    row = conn.execute(
        "SELECT u.id, u.username, u.account_number, u.permanent "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.token = ? AND s.created_at > ?",
        (token, int(time.time()) - CONFIG["session_days"] * 86400),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "username": row[1],
        "account_number": row[2],
        "permanent": row[3],
    }
