import sqlite3
import time
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

DB = Path("txtwall.db")
TTL_SECONDS = 24 * 3600  # messages auto-delete after 24h
MAX_CT_LEN = 5000        # ciphertext length cap (frontend sends ~700 chars max)
MAX_IV_LEN = 64          # IV length cap (frontend sends 16 chars)
MAX_ROWS = 5000          # hard cap on stored messages
RATE_LIMIT = 5           # posts allowed per window
RATE_WINDOW = 10         # window in seconds

app = FastAPI()

# --- light rate limiting (in-memory, per IP, only on POST) ---
_hits = defaultdict(list)


def _rate_limited(ip: str) -> bool:
    now = time.time()
    _hits[ip] = [t for t in _hits[ip] if now - t < RATE_WINDOW]
    if len(_hits[ip]) >= RATE_LIMIT:
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


def db():
    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, ct TEXT NOT NULL, iv TEXT NOT NULL, created_at INTEGER NOT NULL)"
    )
    return conn


class Post(BaseModel):
    ct: str = Field(max_length=MAX_CT_LEN)
    iv: str = Field(max_length=MAX_IV_LEN)


@app.get("/api/messages")
def messages():
    # reads stay free - no rate limit, no auth
    conn = db()
    rows = conn.execute(
        "SELECT id, ct, iv, created_at FROM messages ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "ct": r[1], "iv": r[2], "created_at": r[3]} for r in rows]


@app.post("/api/post")
def post(p: Post, request: Request):
    ip = request.client.host if request.client else "unknown"
    if _rate_limited(ip):
        return JSONResponse({"ok": False, "error": "slow down"}, status_code=429)

    conn = db()
    conn.execute("DELETE FROM messages WHERE created_at < ?", (int(time.time()) - TTL_SECONDS,))
    # hard cap: keep only the newest MAX_ROWS
    conn.execute(
        "DELETE FROM messages WHERE id NOT IN (SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
        (MAX_ROWS,),
    )
    conn.execute(
        "INSERT INTO messages (ct, iv, created_at) VALUES (?, ?, ?)",
        (p.ct, p.iv, int(time.time())),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


app.mount("/", StaticFiles(directory="static", html=True), name="static")