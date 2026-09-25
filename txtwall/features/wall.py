"""The wall itself: read, post, and the random-message pick."""

import secrets
import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, db, images, security
from ..config import CONFIG
from . import feature

router = APIRouter()


class Post(BaseModel):
    ct: str = Field(default="", max_length=CONFIG["max_ct_len"])
    iv: str = Field(default="", max_length=CONFIG["max_iv_len"])


@router.get("/api/messages")
def list_messages(request: Request):
    """Reads are free — no auth, no rate limit. Anyone can watch the wall."""
    security.mark_viewer(security.client_ip(request))
    conn = db.db()
    db.purge(conn)  # stale posts disappear even if nobody is posting
    rows = conn.execute(
        "SELECT id, ct, iv, image, created_at FROM messages ORDER BY id DESC LIMIT 200"
    ).fetchall()
    reacts = conn.execute(
        "SELECT message_id, emoji, COUNT(*) FROM reactions GROUP BY message_id, emoji"
    ).fetchall()
    conn.close()

    by_msg: dict = {}
    for mid, emoji, n in reacts:
        by_msg.setdefault(mid, {})[emoji] = n

    messages = [
        {
            "id": r[0],
            "ct": r[1],
            "iv": r[2],
            "image": r[3],
            "created_at": r[4],
            "reactions": by_msg.get(r[0], {}),
        }
        for r in rows
    ]
    messages.append({"viewers": security.viewer_count()})
    return messages


@router.get("/api/messages/random")
def random_message():
    conn = db.db()
    db.purge(conn)
    row = conn.execute(
        "SELECT id, ct, iv, image, created_at FROM messages ORDER BY RANDOM() LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        return {"found": False}
    return {
        "found": True,
        "id": row[0],
        "ct": row[1],
        "iv": row[2],
        "image": row[3],
        "created_at": row[4],
    }


@router.post("/api/post")
def post_message(body: Post, request: Request):
    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    user = accounts.current_user(request)
    user_id = user["id"] if user else None
    conn = db.db()
    db.purge(conn)

    used = db.quota_used(conn, user_id, ip, "ct")
    msg_max, _ = db.quota_limits(user_id)
    if used >= msg_max:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"daily message limit reached ({msg_max})"},
            status_code=429,
        )

    now = int(time.time())
    db.enforce_row_cap(conn)
    conn.execute(
        "INSERT INTO messages (ct, iv, image, user_id, ip, created_at) "
        "VALUES (?, ?, NULL, ?, ?, ?)",
        (body.ct, body.iv, user_id, ip, now),
    )
    if user_id:
        conn.execute("UPDATE users SET last_active = ? WHERE id = ?", (now, user_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.post("/api/post/image")
async def post_image(request: Request):
    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    user = accounts.current_user(request)
    user_id = user["id"] if user else None
    conn = db.db()

    used = db.quota_used(conn, user_id, ip, "image")
    _, img_max = db.quota_limits(user_id)
    if used >= img_max:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"daily image limit reached ({img_max})"},
            status_code=429,
        )

    data = await request.body()
    try:
        png = images.process_image(data)
    except ValueError as e:
        conn.close()
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

    name = secrets.token_hex(16) + ".png"
    (db.UPLOADS / name).write_bytes(png)

    now = int(time.time())
    conn.execute(
        "DELETE FROM messages WHERE created_at < ?", (now - CONFIG["ttl_seconds"],)
    )
    db.enforce_row_cap(conn)
    conn.execute(
        "INSERT INTO messages (ct, iv, image, user_id, ip, created_at) "
        "VALUES ('', '', ?, ?, ?, ?)",
        (name, user_id, ip, now),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "image": name}


feature(
    "wall",
    router,
    title="Message wall",
    description="read, post and randomly pick messages. encrypted client-side.",
)
