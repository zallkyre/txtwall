import sqlite3
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

DB = Path("txtwall.db")
TTL_SECONDS = 24 * 3600  # messages auto-delete after 24h

app = FastAPI()


def db():
    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, ct TEXT NOT NULL, iv TEXT NOT NULL, created_at INTEGER NOT NULL)"
    )
    return conn


class Post(BaseModel):
    ct: str
    iv: str


@app.get("/api/messages")
def messages():
    conn = db()
    rows = conn.execute(
        "SELECT id, ct, iv, created_at FROM messages ORDER BY id DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "ct": r[1], "iv": r[2], "created_at": r[3]} for r in rows]


@app.post("/api/post")
def post(p: Post):
    conn = db()
    conn.execute("DELETE FROM messages WHERE created_at < ?", (int(time.time()) - TTL_SECONDS,))
    conn.execute(
        "INSERT INTO messages (ct, iv, created_at) VALUES (?, ?, ?)",
        (p.ct, p.iv, int(time.time())),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


app.mount("/", StaticFiles(directory="static", html=True), name="static")