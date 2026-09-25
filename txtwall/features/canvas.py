"""The pixel canvas.

One shared grid, no expiry, and a hard daily allowance that the client
cannot get around. Every limit below is checked on the server, inside the
request, before anything is written:

* **cooldown** — seconds since this identity's last pixel
* **daily allowance** — ``base + credits``, counted in a database row
  keyed by (UTC day, identity), so reloading the page changes nothing
* **rate limit** — a blunt per-IP brake on request volume

The anonymous identity is a signed device cookie (see ``identity.py``), so
refreshing, clearing JS or editing localStorage all leave the counter
exactly where it was.
"""

import time

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, db, identity, security
from ..config import CONFIG, GRID_SIZE, PALETTE
from . import feature

router = APIRouter()

# events older than this are dropped from the feed; the feed only needs to
# bridge the gap between two polls, and this table would grow forever
FEED_RETENTION = 20000


class Place(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    color: str = Field(min_length=4, max_length=7)


class Erase(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)


def _state(conn, ident: str, user) -> dict:
    """Everything the client needs to draw the allowance meter."""
    user_id = user["id"] if user else None
    allow = db.allowance(conn, user_id)
    used = db.used_today(conn, ident)
    return {
        "used": used,
        "base": allow["base"],
        "credits": allow["credits"],
        "allowed": allow["allowed"],
        "left": max(0, allow["allowed"] - used),
        "cooldown": db.cooldown_left(conn, ident),
    }


def _in_bounds(x: int, y: int) -> bool:
    return 0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE


def _trim_feed(conn) -> None:
    conn.execute(
        "DELETE FROM pixel_events WHERE id <= ("
        "  SELECT COALESCE(MAX(id), 0) - ? FROM pixel_events)",
        (FEED_RETENTION,),
    )


@router.get("/api/canvas")
def get_canvas(request: Request, since: int = 0):
    """Full canvas on first load, or just the changes since ``since``.

    ``cursor`` is the id of the newest event. The client stores it and
    passes it back next poll, so it only ever repaints changed cells.
    """
    user = accounts.current_user(request)
    ident, _ = identity.identity(request, user)
    conn = db.db()

    cursor = db.canvas_cursor(conn)
    state = _state(conn, ident, user)

    if since <= 0:
        pixels = [
            [row["x"], row["y"], row["color"]]
            for row in conn.execute("SELECT x, y, color FROM pixels").fetchall()
        ]
        conn.close()
        return {
            "size": GRID_SIZE,
            "palette": PALETTE,
            "painted": len(pixels),
            "pixels": pixels,
            "cursor": cursor,
            "state": state,
        }

    events = [
        [row["id"], row["x"], row["y"], row["color"]]
        for row in conn.execute(
            "SELECT id, x, y, color FROM pixel_events WHERE id > ? ORDER BY id LIMIT 2000",
            (since,),
        ).fetchall()
    ]
    conn.close()
    return {
        "size": GRID_SIZE,
        "palette": PALETTE,
        "events": events,
        "cursor": events[-1][0] if events else since,
        "state": state,
    }


def _consume(conn, ident: str, user) -> tuple:
    """Charge one pixel against the allowance. Returns (ok, error, state).

    The free daily allowance is spent first; only once it is gone does a
    credit get drawn down. Because ``allowed`` is derived as
    ``base + credits``, spending a credit lowers ``allowed`` by one too, so
    the remaining count falls by exactly one either way.
    """
    user_id = user["id"] if user else None
    allow = db.allowance(conn, user_id)
    used = db.used_today(conn, ident)

    if used >= allow["allowed"]:
        return False, "daily limit reached", None

    if used >= allow["base"] and not db.spend_credit(conn, user_id, 1):
        return False, "daily limit reached", None

    db.bump_used(conn, ident)
    db.set_cooldown(conn, ident)
    return True, "", _state(conn, ident, user)


@router.post("/api/pixel")
def place_pixel(body: Place, request: Request):
    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    if not _in_bounds(body.x, body.y):
        return JSONResponse({"ok": False, "error": "out of bounds"}, status_code=400)

    color = body.color.strip().lower()
    if color not in PALETTE:
        return JSONResponse(
            {"ok": False, "error": "colour is not on the palette"}, status_code=400
        )

    user = accounts.current_user(request)
    ident, _ = identity.identity(request, user)

    conn = db.db()
    wait = db.cooldown_left(conn, ident)
    if wait > 0:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"wait {wait}s", "cooldown": wait}, status_code=429
        )

    ok, err, state = _consume(conn, ident, user)
    if not ok:
        state = _state(conn, ident, user)
        conn.close()
        return JSONResponse({"ok": False, "error": err, "state": state}, status_code=429)

    conn.execute(
        "INSERT INTO pixels (x, y, color, owner, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(x, y) DO UPDATE SET color = excluded.color, "
        "owner = excluded.owner, created_at = excluded.created_at",
        (body.x, body.y, color, ident, int(time.time())),
    )
    event = db.log_event(conn, body.x, body.y, color)
    _trim_feed(conn)
    conn.commit()
    conn.close()

    return {"ok": True, "x": body.x, "y": body.y, "color": color, "event": event, "state": state}


@router.post("/api/pixel/erase")
def erase_pixel(body: Erase, request: Request):
    """Clear a cell. Costs a pixel, because free erasing is just vandalism."""
    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    if not _in_bounds(body.x, body.y):
        return JSONResponse({"ok": False, "error": "out of bounds"}, status_code=400)

    user = accounts.current_user(request)
    ident, _ = identity.identity(request, user)

    conn = db.db()

    # check the target first: erasing empty canvas should be free, or
    # people grief the quota by wiping blank space
    target = conn.execute(
        "SELECT color FROM pixels WHERE x = ? AND y = ?", (body.x, body.y)
    ).fetchone()
    if not target:
        state = _state(conn, ident, user)
        conn.close()
        return {"ok": True, "noop": True, "state": state}

    wait = db.cooldown_left(conn, ident)
    if wait > 0:
        state = _state(conn, ident, user)
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"wait {wait}s", "cooldown": wait, "state": state},
            status_code=429,
        )

    if CONFIG["erase_costs_pixel"]:
        ok, err, state = _consume(conn, ident, user)
        if not ok:
            conn.close()
            return JSONResponse({"ok": False, "error": err}, status_code=429)
    else:
        db.set_cooldown(conn, ident)
        state = _state(conn, ident, user)

    conn.execute("DELETE FROM pixels WHERE x = ? AND y = ?", (body.x, body.y))
    event = db.log_event(conn, body.x, body.y, None)
    _trim_feed(conn)
    conn.commit()
    conn.close()
    return {"ok": True, "x": body.x, "y": body.y, "event": event, "state": state}


feature(
    "canvas",
    router,
    title="Pixel canvas",
    description="a shared grid. 10 pixels a day, 100 with an account.",
)
