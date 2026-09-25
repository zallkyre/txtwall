"""Database access and the retention rules.

One sqlite file holds everything. The important promise this module keeps:
messages, images and sessions are *pure-deleted* once they pass their TTL.
Accounts are never touched.
"""

import shutil
import sqlite3
import time
from pathlib import Path

from .config import CONFIG, DB_PATH, UPLOADS

_last_vacuum = 0.0

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ct TEXT NOT NULL DEFAULT '',
        iv TEXT NOT NULL DEFAULT '',
        image TEXT,
        user_id INTEGER,
        ip TEXT,
        created_at INTEGER NOT NULL
    )""",
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
    """CREATE TABLE IF NOT EXISTS reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message_id INTEGER NOT NULL,
        emoji TEXT NOT NULL,
        ip TEXT,
        created_at INTEGER NOT NULL
    )""",
)

# columns added after the first release, applied to old databases
MIGRATIONS = {
    "messages": [
        ("image", "ALTER TABLE messages ADD COLUMN image TEXT"),
        ("user_id", "ALTER TABLE messages ADD COLUMN user_id INTEGER"),
        ("ip", "ALTER TABLE messages ADD COLUMN ip TEXT"),
    ],
    "users": [
        ("last_active", "ALTER TABLE users ADD COLUMN last_active INTEGER NOT NULL DEFAULT 0"),
    ],
}


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    for ddl in SCHEMA:
        conn.execute(ddl)
    for table, changes in MIGRATIONS.items():
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for col, ddl in changes:
            if col not in cols:
                conn.execute(ddl)
    conn.commit()
    return conn


def day_start() -> int:
    """UTC midnight — quotas reset once a day, not every rolling 24h."""
    now = int(time.time())
    return now - (now % 86400)


def storage_factor() -> float:
    """How much of the daily caps to allow, based on disk usage.

    Returns 1.0 when storage is fine and shrinks gently as the disk
    fills. Never drops below the smallest cap_shrink factor, so posting
    always stays possible.
    """
    try:
        total, _, free = shutil.disk_usage(UPLOADS)
        used = 1.0 - (free / total) if total else 0.0
    except Exception:
        return 1.0
    factor = 1.0
    for threshold, value in CONFIG["cap_shrink"]:
        if used < threshold:
            return factor
        factor = value
    return factor


def quota_limits(user_id) -> tuple:
    if user_id:
        msg, img = CONFIG["user_msg_daily"], CONFIG["user_img_daily"]
    else:
        msg, img = CONFIG["anon_msg_daily"], CONFIG["anon_img_daily"]
    factor = storage_factor()
    return max(1, int(msg * factor)), max(1, int(img * factor))


def quota_used(conn, user_id, ip, kind: str) -> int:
    """Messages used today. kind: 'ct' = text, 'image' = has a picture."""
    day = day_start()
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


def purge(conn) -> None:
    """Delete everything past its TTL, then shrink the file.

    Messages, image files and stale sessions go. Accounts stay forever.
    VACUUM is throttled to once an hour so the DB file actually shrinks
    without slowing every request down.
    """
    global _last_vacuum
    cutoff = int(time.time()) - CONFIG["ttl_seconds"]

    for (img,) in conn.execute(
        "SELECT image FROM messages WHERE created_at < ? AND image IS NOT NULL", (cutoff,)
    ).fetchall():
        try:
            (UPLOADS / Path(img).name).unlink(missing_ok=True)
        except Exception:
            pass

    conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff,))
    conn.execute(
        "DELETE FROM reactions WHERE message_id NOT IN (SELECT id FROM messages)"
    )
    conn.execute("DELETE FROM sessions WHERE created_at < ?", (cutoff,))
    conn.commit()

    now = time.time()
    if now - _last_vacuum > 3600:
        try:
            conn.execute("VACUUM")
            _last_vacuum = now
        except Exception:
            pass


def enforce_row_cap(conn) -> None:
    """Keep only the newest N messages, whatever the TTL says."""
    conn.execute(
        "DELETE FROM messages WHERE id NOT IN "
        "(SELECT id FROM messages ORDER BY id DESC LIMIT ?)",
        (CONFIG["max_rows"],),
    )
