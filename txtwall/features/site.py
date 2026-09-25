"""Site-wide endpoints: public config and wall stats.

``/api/config`` is what lets the front end render itself from settings —
support address, site name, which features exist — instead of hardcoding
them in the HTML. A developer changes config.json, not markup.
"""

import time

from fastapi import APIRouter

from .. import db
from ..config import public_config
from . import feature

router = APIRouter()


@router.get("/api/config")
def site_config():
    return public_config()


@router.get("/api/stats")
def stats():
    """Small numbers for the support panel."""
    conn = db.db()
    now = int(time.time())
    total = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    today = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE created_at >= ?", (db.day_start(),)
    ).fetchone()[0]
    accounts = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return {
        "messages": total,
        "messages_today": today,
        "accounts": accounts,
        "ttl_hours": round(db.CONFIG["ttl_seconds"] / 3600, 1),
    }


feature("site", router, title="Site config and stats", always=True)
