"""Site-wide endpoints: public config and canvas stats.

``/api/config`` is what lets the front end render itself from settings —
site name, grid size, palette, which features exist — instead of hardcoding
them in the HTML. A developer changes config.json, not markup.
"""

import time

from fastapi import APIRouter

from .. import db
from ..config import GRID_SIZE, public_config
from . import feature

router = APIRouter()


@router.get("/api/config")
def site_config():
    return public_config()


@router.get("/api/stats")
def stats():
    """Small numbers for the support panel."""
    conn = db.db()
    painted = db.painted_count(conn)
    today = conn.execute(
        "SELECT COUNT(*) FROM pixel_events WHERE color IS NOT NULL AND created_at >= ?",
        (db.day_start(),),
    ).fetchone()[0]
    accounts = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    credits = conn.execute(
        "SELECT COALESCE(SUM(remaining), 0) FROM credits"
    ).fetchone()[0]
    open_reports = conn.execute(
        "SELECT COUNT(*) FROM reports WHERE resolved = 0"
    ).fetchone()[0]
    # which colours people actually reach for; the palette's real hit rate
    palette_use = [
        {"color": r["color"], "count": r["n"]}
        for r in conn.execute(
            "SELECT color, COUNT(*) AS n FROM pixels GROUP BY color ORDER BY n DESC"
        )
    ]
    artists = conn.execute(
        "SELECT COUNT(DISTINCT owner) FROM pixels"
    ).fetchone()[0]
    conn.close()
    return {
        "painted": painted,
        "cells": GRID_SIZE * GRID_SIZE,
        "painted_today": today,
        "accounts": accounts,
        "artists": artists,
        "credits_outstanding": credits,
        "open_reports": open_reports,
        "palette_use": palette_use,
    }


def _label(conn, ident: str) -> str:
    """Turn a stored owner key into something showable.

    Accounts are stored as ``u:<id>`` and can be named; anonymous devices
    are ``d:<token>`` and deliberately stay nameless.
    """
    if ident.startswith("u:"):
        row = conn.execute(
            "SELECT username FROM users WHERE id = ?", (ident[2:],)
        ).fetchone()
        return row["username"] if row else "account " + ident[2:]
    return "anon"


@router.get("/api/leaderboard")
def leaderboard(limit: int = 10):
    """Who has painted the most cells that are still standing."""
    limit = max(1, min(50, limit))
    conn = db.db()
    rows = conn.execute(
        "SELECT owner, COUNT(*) AS n FROM pixels GROUP BY owner ORDER BY n DESC, owner LIMIT ?",
        (limit,),
    ).fetchall()
    out = [
        {"rank": i + 1, "name": _label(conn, r["owner"]), "pixels": r["n"]}
        for i, r in enumerate(rows)
    ]
    conn.close()
    return {"artists": out}


@router.get("/api/activity")
def activity(limit: int = 24):
    """The most recent placements, newest first, for the live feed."""
    limit = max(1, min(100, limit))
    conn = db.db()
    rows = conn.execute(
        "SELECT id, x, y, color, created_at FROM pixel_events "
        "WHERE color IS NOT NULL ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = [
        {
            "id": r["id"],
            "x": r["x"],
            "y": r["y"],
            "color": r["color"],
            "ago": max(0, int(time.time()) - int(r["created_at"])),
        }
        for r in rows
    ]
    conn.close()
    return {"events": out}


feature("site", router, title="Site config and stats", always=True)
