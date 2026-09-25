import hashlib
import io
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image

# ============================================================
#  CONFIG — edit everything here, nothing else
# ============================================================
CONFIG = {
    # --- messages ---
    "ttl_seconds": 24 * 3600,            # messages auto-delete after 24h
    "max_ct_len": 5000,                  # ciphertext length cap
    "max_iv_len": 64,                    # IV length cap
    "max_rows": 5000,                    # hard cap on stored messages

    # --- rate limiting (per IP, POST only) ---
    "rate_limit": 5,                     # posts allowed per window
    "rate_window": 10,                   # window in seconds

    # --- daily quotas ---
    "anon_msg_daily": 5,                 # anonymous: messages per day
    "anon_img_daily": 1,                 # anonymous: images per day
    "user_msg_daily": 250,               # account: messages per day
    "user_img_daily": 50,                # account: images per day

    # --- accounts ---
    "account_number_digits": 45,         # account number length (32-64)
    "session_days": 30,                  # session lifetime
    "username_min": 3,
    "username_max": 32,
    "password_min": 4,
    "password_max": 64,

    # --- images ---
    "max_image_bytes": 5 * 1024 * 1024,  # max upload size (5MB)
    "image_max_dim": 1080,               # images scaled to fit this box (1080x1080)
    "uploads_dir": "uploads",            # where images are stored
}

DB = Path("txtwall.db")
UPLOADS = Path(CONFIG["uploads_dir"])
UPLOADS.mkdir(exist_ok=True)

app = FastAPI()

# --- light rate limiting (in-memory, per IP, only on POST) ---
_hits = defaultdict(list)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < CONFIG["rate_window"]]
    if len(_hits[ip]) >= CONFIG["rate_limit"]:
        return True
    _hits[ip].append(now)
    if len(_hits) > 10000:  # keep the dict bounded
        _hits.clear()
    return False


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


# ============================================================
#  DATABASE
# ============================================================
def db():
    conn = sqlite3.connect(DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ct TEXT NOT NULL DEFAULT '',
            iv TEXT NOT NULL DEFAULT '',
            image TEXT,
            user_id INTEGER,
            ip TEXT,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            account_number TEXT UNIQUE NOT NULL,
            permanent INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )"""
    )
    # migrate old tables (add columns if missing)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(messages)")}
    for col, ddl in [
        ("image", "ALTER TABLE messages ADD COLUMN image TEXT"),
        ("user_id", "ALTER TABLE messages ADD COLUMN user_id INTEGER"),
        ("ip", "ALTER TABLE messages ADD COLUMN ip TEXT"),
    ]:
        if col not in cols:
            conn.execute(ddl)
    conn.commit()
    return conn


# ============================================================
#  AUTH HELPERS
# ============================================================
def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 100_000
    ).hex()


def _new_account_number() -> str:
    digits = CONFIG["account_number_digits"]
    # first digit never 0 so the number keeps its full length
    return str(secrets.randbelow(9) + 1) + "".join(
        str(secrets.randbelow(10)) for _ in range(digits - 1)
    )


def _new_session(conn, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, int(time.time())),
    )
    conn.commit()
    return token


def _user_from_request(request: Request):
    token = request.cookies.get("session")
    if not token:
        return None
    conn = db()
    row = conn.execute(
        "SELECT u.id, u.username, u.account_number, u.permanent FROM sessions s "
        "JOIN users u ON u.id = s.user_id WHERE s.token = ? AND s.created_at > ?",
        (token, int(time.time()) - CONFIG["session_days"] * 86400),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "account_number": row[2], "permanent": row[3]}


def _day_start() -> int:
    # UTC day boundary — quotas reset at midnight UTC
    return int(time.time()) - (int(time.time()) % 86400)


def _quota_used(conn, user_id, ip, kind: str) -> int:
    day = _day_start()
    # kind: "ct" = text message (non-empty ciphertext), "image" = has an image
    cond = "ct != ''" if kind == "ct" else "image IS NOT NULL"
    if user_id:
        return conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE user_id = ? AND created_at >= ? AND {cond}",
            (user_id, day),
        ).fetchone()[0]
    return conn.execute(
        f"SELECT COUNT(*) FROM messages WHERE ip = ? AND created_at >= ? AND {cond}",
        (ip, day),
    ).fetchone()[0]


def _quota_limits(user_id):
    if user_id:
        return CONFIG["user_msg_daily"], CONFIG["user_img_daily"]
    return CONFIG["anon_msg_daily"], CONFIG["anon_img_daily"]


# ============================================================
#  IMAGE HANDLING — validated, re-encoded, scaled
# ============================================================
_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "PNG",
    b"\xff\xd8\xff": "JPEG",
    b"GIF87a": "GIF",
    b"GIF89a": "GIF",
    b"RIFF": "WEBP",  # RIFF....WEBP
}


def _detect_format(data: bytes):
    for magic, fmt in _MAGIC.items():
        if data.startswith(magic):
            if fmt == "WEBP" and data[8:12] != b"WEBP":
                continue
            return fmt
    return None


def _process_image(data: bytes) -> bytes:
    """Validate magic bytes, re-encode via Pillow, scale to fit 1080x1080.
    Returns PNG bytes. Raises ValueError on anything suspicious."""
    if len(data) > CONFIG["max_image_bytes"]:
        raise ValueError("image too large")
    if _detect_format(data) is None:
        raise ValueError("unsupported image type")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise ValueError("corrupt image")
    # strip metadata / re-encode (kills embedded payloads)
    img = img.convert("RGB")
    img.thumbnail((CONFIG["image_max_dim"], CONFIG["image_max_dim"]), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


# ============================================================
#  API
# ============================================================
class Post(BaseModel):
    ct: str = Field(default="", max_length=CONFIG["max_ct_len"])
    iv: str = Field(default="", max_length=CONFIG["max_iv_len"])


class Signup(BaseModel):
    username: str = Field(min_length=CONFIG["username_min"], max_length=CONFIG["username_max"])
    password: str = Field(min_length=CONFIG["password_min"], max_length=CONFIG["password_max"])


class Login(BaseModel):
    username: str = Field(min_length=1, max_length=CONFIG["username_max"])
    password: str = Field(min_length=1, max_length=CONFIG["password_max"])


class Permanent(BaseModel):
    permanent: bool


@app.get("/api/messages")
def messages():
    # reads stay free - no rate limit, no auth
    conn = db()
    # purge expired messages on every read too, so stale posts
    # auto-delete even when nobody posts
    cutoff = int(time.time()) - CONFIG["ttl_seconds"]
    expired = conn.execute(
        "SELECT image FROM messages WHERE created_at < ? AND image IS NOT NULL",
        (cutoff,),
    ).fetchall()
    conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
    conn.commit()
    # delete orphaned image files
    for (img,) in expired:
        try:
            (UPLOADS / img).unlink(missing_ok=True)
        except Exception:
            pass
    rows = conn.execute(
        "SELECT id, ct, iv, image, created_at FROM messages ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "ct": r[1], "iv": r[2], "image": r[3], "created_at": r[4]}
        for r in rows
    ]


@app.post("/api/post")
def post(p: Post, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        return JSONResponse({"ok": False, "error": "slow down"}, status_code=429)

    user = _user_from_request(request)
    user_id = user["id"] if user else None
    conn = db()
    msg_used = _quota_used(conn, user_id, ip, "ct")
    msg_max, _ = _quota_limits(user_id)
    if msg_used >= msg_max:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"daily message limit reached ({msg_max})"},
            status_code=429,
        )

    conn.execute("DELETE FROM messages WHERE created_at < ?", (int(time.time()) - CONFIG["ttl_seconds"],))
    # hard cap: keep only the newest MAX_ROWS
    conn.execute(
        "DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
        (CONFIG["max_rows"],),
    )
    conn.execute(
        "INSERT INTO messages (ct, iv, image, user_id, ip, created_at) VALUES (?, ?, NULL, ?, ?, ?)",
        (p.ct, p.iv, user_id, ip, int(time.time())),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/post/image")
async def post_image(request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        return JSONResponse({"ok": False, "error": "slow down"}, status_code=429)

    user = _user_from_request(request)
    user_id = user["id"] if user else None
    conn = db()
    img_used = _quota_used(conn, user_id, ip, "image")
    _, img_max = _quota_limits(user_id)
    if img_used >= img_max:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"daily image limit reached ({img_max})"},
            status_code=429,
        )

    data = await request.body()
    try:
        png = _process_image(data)
    except ValueError as e:
        conn.close()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    name = secrets.token_hex(16) + ".png"
    (UPLOADS / name).write_bytes(png)

    conn.execute("DELETE FROM messages WHERE created_at < ?", (int(time.time()) - CONFIG["ttl_seconds"],))
    conn.execute(
        "DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
        (CONFIG["max_rows"],),
    )
    conn.execute(
        "INSERT INTO messages (ct, iv, image, user_id, ip, created_at) VALUES ('', '', ?, ?, ?, ?)",
        (name, user_id, ip, int(time.time())),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "image": name}


# ============================================================
#  ACCOUNTS
# ============================================================
@app.post("/api/signup")
def signup(body: Signup, response: Response):
    username = body.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", username):
        return JSONResponse({"ok": False, "error": "username: letters, numbers, underscore only"}, status_code=400)

    conn = db()
    if conn.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
        conn.close()
        return JSONResponse({"ok": False, "error": "username taken"}, status_code=409)

    salt = secrets.token_hex(16)
    account_number = _new_account_number()
    # keep generating until unique (rotation collisions are astronomically unlikely)
    while conn.execute("SELECT 1 FROM users WHERE account_number = ?", (account_number,)).fetchone():
        account_number = _new_account_number()

    cur = conn.execute(
        "INSERT INTO users (username, password_hash, salt, account_number, permanent, created_at) "
        "VALUES (?, ?, ?, ?, 0, ?)",
        (username, _hash_password(body.password, salt), salt, account_number, int(time.time())),
    )
    token = _new_session(conn, cur.lastrowid)
    conn.close()

    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=CONFIG["session_days"] * 86400)
    return {"ok": True, "username": username, "account_number": account_number, "permanent": False}


@app.post("/api/login")
def login(body: Login, response: Response):
    conn = db()
    row = conn.execute(
        "SELECT id, username, password_hash, salt, account_number, permanent FROM users WHERE username = ?",
        (body.username.strip(),),
    ).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"ok": False, "error": "wrong username or password"}, status_code=401)

    user_id, username, pw_hash, salt, account_number, permanent = row
    if _hash_password(body.password, salt) != pw_hash:
        conn.close()
        return JSONResponse({"ok": False, "error": "wrong username or password"}, status_code=401)

    # rotate account number on every login unless the user locked it permanent
    if not permanent:
        account_number = _new_account_number()
        while conn.execute("SELECT 1 FROM users WHERE account_number = ?", (account_number,)).fetchone():
            account_number = _new_account_number()
        conn.execute("UPDATE users SET account_number = ? WHERE id = ?", (account_number, user_id))
        conn.commit()

    token = _new_session(conn, user_id)
    conn.close()

    response.set_cookie("session", token, httponly=True, samesite="lax", max_age=CONFIG["session_days"] * 86400)
    return {"ok": True, "username": username, "account_number": account_number, "permanent": bool(permanent)}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    user = _user_from_request(request)
    ip = request.client.host if request.client else "unknown"

    conn = db()
    if user:
        msg_used = _quota_used(conn, user["id"], None, "ct")
        img_used = _quota_used(conn, user["id"], None, "image")
        msg_max, img_max = _quota_limits(user["id"])
        conn.close()
        return {
            "ok": True,
            "logged_in": True,
            "username": user["username"],
            "account_number": user["account_number"],
            "permanent": bool(user["permanent"]),
            "quota": {"messages": [msg_used, msg_max], "images": [img_used, img_max]},
        }

    # anonymous: report the daily caps so the UI can show remaining posts
    msg_used = _quota_used(conn, None, ip, "ct")
    img_used = _quota_used(conn, None, ip, "image")
    msg_max, img_max = _quota_limits(None)
    conn.close()
    return {
        "ok": True,
        "logged_in": False,
        "quota": {"messages": [msg_used, msg_max], "images": [img_used, img_max]},
    }


@app.post("/api/account/permanent")
def set_permanent(body: Permanent, request: Request):
    user = _user_from_request(request)
    if not user:
        return JSONResponse({"ok": False, "error": "not logged in"}, status_code=401)
    conn = db()
    conn.execute("UPDATE users SET permanent = ? WHERE id = ?", (1 if body.permanent else 0, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True, "permanent": body.permanent}


app.mount("/uploads", StaticFiles(directory=str(UPLOADS)), name="uploads")
app.mount("/", StaticFiles(directory="static", html=True), name="static")