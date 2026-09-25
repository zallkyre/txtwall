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
    conn.close()
    return {
        "painted": painted,
        "cells": GRID_SIZE * GRID_SIZE,
        "painted_today": today,
        "accounts": accounts,
        "credits_outstanding": credits,
        "open_reports": open_reports,
    }


feature("site", router, title="Site config and stats", always=True)
