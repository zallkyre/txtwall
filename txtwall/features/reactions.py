"""Emoji reactions."""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db, security
from . import feature

router = APIRouter()


class React(BaseModel):
    message_id: int
    emoji: str = Field(min_length=1, max_length=8)


@router.post("/api/react")
def react(body: React, request: Request):
    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    conn = db.db()
    if not conn.execute(
        "SELECT 1 FROM messages WHERE id = ?", (body.message_id,)
    ).fetchone():
        conn.close()
        return JSONResponse({"ok": False, "error": "message gone"}, status_code=404)

    conn.execute(
        "INSERT INTO reactions (message_id, emoji, ip, created_at) VALUES (?, ?, ?, ?)",
        (body.message_id, body.emoji, ip, int(time.time())),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


feature(
    "reactions",
    router,
    title="Reactions",
    description="one-tap emoji reactions on any message.",
)
