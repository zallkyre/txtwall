"""Pixel credits: bought, granted by hand, or earned.

Credits are a balance, not a multiplier. ``allowed today = base + credits``
and a credit is only spent once the free daily allowance is used up, so a
purchase of 500 gives 600 today, 500 tomorrow, and settles back to a clean
100 a day once they are gone.

Two ways to get them today, both live:

* **/grant from Discord.** ``/grant username 500`` in the bot calls
  ``POST /api/admin/grant`` with the shared admin token. This is the
  "pay me however and I'll add them" path, and it needs no payment
  processor at all.
* **Reporting abuse.** A report the owner marks valid pays the reporter.

Stripe is wired up in ``payments.py`` but disabled, because payment
processors require an 18+ account holder. Turn it on later and nothing
here changes.
"""

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, db, identity
from ..config import CONFIG
from . import feature

router = APIRouter()


class Grant(BaseModel):
    username: str = Field(min_length=1, max_length=CONFIG["username_max"])
    pixels: int = Field(ge=1, le=1_000_000)
    note: str = Field(default="", max_length=200)


class ResolveReport(BaseModel):
    report_id: int = Field(ge=1)
    valid: bool = True
    reward: bool = True


def _authorised(token: str | None) -> bool:
    expected = CONFIG.get("admin_token") or ""
    return bool(expected) and bool(token) and token == expected


@router.get("/api/credits")
def my_credits(request: Request):
    user = accounts.current_user(request)
    conn = db.db()
    if not user:
        conn.close()
        return {"ok": True, "logged_in": False, "balance": 0, "ledger": []}

    allow = db.allowance(conn, user["id"])
    ledger = [
        {
            "amount": row["amount"],
            "remaining": row["remaining"],
            "kind": row["kind"],
            "source": row["source"],
            "created_at": row["created_at"],
        }
        for row in conn.execute(
            "SELECT * FROM credits WHERE user_id = ? ORDER BY id DESC LIMIT 25", (user["id"],)
        ).fetchall()
    ]
    conn.close()
    return {
        "ok": True,
        "logged_in": True,
        "balance": allow["credits"],
        "daily_base": allow["base"],
        "ledger": ledger,
    }


@router.post("/api/admin/grant")
def admin_grant(body: Grant, authorization: str = Header(default="")):
    """Credit an account by name. Called by the Discord bot's /grant."""
    token = authorization.replace("Bearer ", "").strip()
    if not _authorised(token):
        return JSONResponse({"ok": False, "error": "not authorised"}, status_code=401)

    conn = db.db()
    user = conn.execute(
        "SELECT id, username FROM users WHERE username = ?", (body.username.strip(),)
    ).fetchone()
    if not user:
        conn.close()
        return JSONResponse(
            {"ok": False, "error": f"no account called {body.username!r}"}, status_code=404
        )

    db.grant_credit(
        conn, user["id"], body.pixels, "grant", "discord", body.note or "granted via discord"
    )
    balance = db.credit_balance(conn, user["id"])
    conn.commit()
    conn.close()
    return {
        "ok": True,
        "username": user["username"],
        "granted": body.pixels,
        "balance": balance,
    }


@router.get("/api/admin/reports")
def list_reports(authorization: str = Header(default="")):
    token = authorization.replace("Bearer ", "").strip()
    if not _authorised(token):
        return JSONResponse({"ok": False, "error": "not authorised"}, status_code=401)

    conn = db.db()
    rows = [
        {
            "id": row["id"],
            "x": row["x"],
            "y": row["y"],
            "reason": row["reason"],
            "created_at": row["created_at"],
            "resolved": bool(row["resolved"]),
            "rewarded": bool(row["rewarded"]),
            "reporter": row["user_id"],
        }
        for row in conn.execute("SELECT * FROM reports ORDER BY id DESC LIMIT 50").fetchall()
    ]
    conn.close()
    return {"ok": True, "reports": rows}


@router.post("/api/admin/resolve-report")
def resolve_report(body: ResolveReport, authorization: str = Header(default="")):
    """Mark a report handled, optionally paying the reporter for it."""
    token = authorization.replace("Bearer ", "").strip()
    if not _authorised(token):
        return JSONResponse({"ok": False, "error": "not authorised"}, status_code=401)

    conn = db.db()
    row = conn.execute("SELECT * FROM reports WHERE id = ?", (body.report_id,)).fetchone()
    if not row:
        conn.close()
        return JSONResponse({"ok": False, "error": "no such report"}, status_code=404)

    paid = 0
    if body.valid and body.reward and row["user_id"] and not row["rewarded"]:
        amount = CONFIG["credit_reward_per_report"]
        db.grant_credit(
            conn, row["user_id"], amount, "reward", "report", f"report {body.report_id}"
        )
        paid = amount

    conn.execute(
        "UPDATE reports SET resolved = ?, rewarded = ? WHERE id = ?",
        (1 if body.valid else 0, 1 if paid else row["rewarded"], body.report_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "rewarded": paid}


feature(
    "credits",
    router,
    title="Pixel credits",
    description="extra pixels on top of the daily allowance.",
)
