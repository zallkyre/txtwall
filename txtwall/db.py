"""Database access for the pixel canvas.

One sqlite file holds everything. Three ideas matter here:

1. **Nothing expires.** There is no TTL and no background purge. Pixels
   stay until the owner explicitly wipes the canvas.
2. **Daily allowances are rows, not memory.** ``pixel_usage`` is keyed by
   (day, identity), so the counters survive a restart, a reload, and
   somebody clearing their browser.
3. **Credits are a separate pool.** They are only spent once the free
   daily allowance is used up, which is what makes a purchase a burst of
   extra capacity rather than a permanent multiplier.
"""

import sqlite3
import time

from .config import CONFIG, DB_PATH

SCHEMA = (
    # --- current state of the canvas: one row per painted cell ---------
    """CREATE TABLE IF NOT EXISTS pixels (
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        color TEXT NOT NULL,
        owner TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        PRIMARY KEY (x, y)
    )""",
    # --- append-only change log, drives the live poll feed -------------
    # color NULL means "this cell was erased".
    """CREATE TABLE IF NOT EXISTS pixel_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        color TEXT,
        created_at INTEGER NOT NULL
    )""",
    # --- daily counters, keyed by day + identity -----------------------
    """CREATE TABLE IF NOT EXISTS pixel_usage (
        day INTEGER NOT NULL,
        ident TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (day, ident)
    )""",
    # --- last placement, for the cooldown ------------------------------
    """CREATE TABLE IF NOT EXISTS pixel_cooldown (
        ident TEXT PRIMARY KEY,
        last_at INTEGER NOT NULL
    )""",
    # --- purchased and earned pixels -----------------------------------
    # one row per grant; `remaining` is drawn down as they are spent.
    """CREATE TABLE IF NOT EXISTS credits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        kind TEXT NOT NULL,
        amount INTEGER NOT NULL,
        remaining INTEGER NOT NULL,
        source TEXT NOT NULL,
        ref TEXT,
        created_at INTEGER NOT NULL
    )""",
    # --- signup throttling, hashed IP per week -------------------------
    """CREATE TABLE IF NOT EXISTS signup_limits (
        ip_hash TEXT NOT NULL,
        week INTEGER NOT NULL,
        count INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (ip_hash, week)
    )""",
    # --- reports, so a confirmed one can pay out credits ----------------
    """CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        ip TEXT,
        user_id INTEGER,
        created_at INTEGER NOT NULL,
        resolved INTEGER NOT NULL DEFAULT 0,
        rewarded INTEGER NOT NULL DEFAULT 0
    )""",
    # --- accounts -------------------------------------------------------
    """CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        account_number TEXT UNIQUE NOT NULL,
        permanent INTEGER NOT NULL DEFAULT 0,
        created_at INTEGER NOT NULL,
        last_active INTEGER NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL
    )""",
)

# columns added after a release, applied to old databases
MIGRATIONS = {
    "users": [
        ("last_active", "ALTER TABLE users ADD COLUMN last_active INTEGER NOT NULL DEFAULT 0"),
    ],
}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    for ddl in SCHEMA:
        conn.execute(ddl)
    for table, changes in MIGRATIONS.items():
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in changes:
            if col not in cols:
                conn.execute(ddl)
    conn.commit()
    return conn


def day_start(now: float | None = None) -> int:
    """UTC midnight — allowances reset once a day, not every rolling 24h."""
    ts = int(time.time() if now is None else now)
    return ts - (ts % 86400)


def week_start(now: float | None = None) -> int:
    """The Monday 00:00 UTC at or before now, as a unix timestamp."""
    ts = int(time.time() if now is None else now)
    midnight = day_start(ts)
    # unix epoch was a Thursday, so offset by 3 days to land on Monday.
    return midnight - ((midnight // 86400 + 3) % 7) * 86400


def daily_base(user_id) -> int:
    """Free pixels per day. Accounts get the bigger number."""
    return CONFIG["user_pixel_daily"] if user_id else CONFIG["anon_pixel_daily"]


def credit_balance(conn, user_id) -> int:
    """Pixels the user has bought or earned and not yet spent."""
    if not user_id:
        return 0
    row = conn.execute(
        "SELECT COALESCE(SUM(remaining), 0) FROM credits WHERE user_id = ?", (user_id,)
    ).fetchone()
    return int(row[0])


def allowance(conn, user_id) -> dict:
    """What this identity may paint today, and how much of it is left.

    ``allowed = base + credits`` where ``credits`` shrinks as they are
    spent, so ``left`` falls by exactly one per pixel no matter which pool
    it came out of.
    """
    base = daily_base(user_id)
    creds = credit_balance(conn, user_id)
    return {"base": base, "credits": creds, "allowed": base + creds}


def spend_credit(conn, user_id, amount: int = 1) -> bool:
    """Draw ``amount`` pixels off the user's credit balance, oldest first.

    Returns False (and changes nothing) when they do not have enough.
    """
    if not user_id:
        return False
    if credit_balance(conn, user_id) < amount:
        return False
    rows = conn.execute(
        "SELECT id, remaining FROM credits "
        "WHERE user_id = ? AND remaining > 0 ORDER BY id",
        (user_id,),
    ).fetchall()
    left = amount
    for row in rows:
        if left <= 0:
            break
        take = min(left, row["remaining"])
        conn.execute(
            "UPDATE credits SET remaining = remaining - ? WHERE id = ?", (take, row["id"])
        )
        left -= take
    return left == 0


def grant_credit(conn, user_id: int, amount: int, kind: str, source: str, ref: str = "") -> None:
    """Add pixels to a user's balance. Used by purchases and rewards."""
    if amount <= 0:
        return
    conn.execute(
        "INSERT INTO credits (user_id, kind, amount, remaining, source, ref, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, kind, amount, amount, source, ref, int(time.time())),
    )


def used_today(conn, ident: str) -> int:
    row = conn.execute(
        "SELECT used FROM pixel_usage WHERE day = ? AND ident = ?", (day_start(), ident)
    ).fetchone()
    return int(row[0]) if row else 0


def bump_used(conn, ident: str) -> int:
    conn.execute(
        "INSERT INTO pixel_usage (day, ident, used) VALUES (?, ?, 1) "
        "ON CONFLICT(day, ident) DO UPDATE SET used = used + 1",
        (day_start(), ident),
    )
    return used_today(conn, ident)


def cooldown_left(conn, ident: str) -> int:
    """Seconds until this identity may paint again. 0 means ready."""
    row = conn.execute(
        "SELECT last_at FROM pixel_cooldown WHERE ident = ?", (ident,)
    ).fetchone()
    if not row:
        return 0
    wait = CONFIG["pixel_cooldown"] - (int(time.time()) - int(row[0]))
    return wait if wait > 0 else 0


def set_cooldown(conn, ident: str) -> None:
    conn.execute(
        "INSERT INTO pixel_cooldown (ident, last_at) VALUES (?, ?) "
        "ON CONFLICT(ident) DO UPDATE SET last_at = excluded.last_at",
        (ident, int(time.time())),
    )


def log_event(conn, x: int, y: int, color: str | None) -> int:
    """Append to the change feed. Returns the new event id (the cursor)."""
    cur = conn.execute(
        "INSERT INTO pixel_events (x, y, color, created_at) VALUES (?, ?, ?, ?)",
        (x, y, color, int(time.time())),
    )
    return int(cur.lastrowid)


def canvas_cursor(conn) -> int:
    row = conn.execute("SELECT COALESCE(MAX(id), 0) FROM pixel_events").fetchone()
    return int(row[0])


def painted_count(conn) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM pixels").fetchone()[0])
