"""Reporting a pixel to the site owner.

The visitor never sees an email form. They type a reason, the server
records it against that cell and forwards it to the Cloudflare mail
worker, which decides whether Groq can answer automatically or a human gets
pinged on Discord.

Two things worth knowing:

* The recipient is fixed in config (``report_email``). A client can never
  choose where mail goes, so this endpoint cannot be used as a relay.
* Reports are stored, not just emailed, so the owner can mark one valid
  later and pay the reporter in credits. That is the "earn pixels" half of
  the economy and it needs no payment processor.
"""

import json
import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, db, security
from ..config import CONFIG, GRID_SIZE
from . import feature

router = APIRouter()

MAX_REASON = 500


class Report(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    reason: str = Field(default="", max_length=MAX_REASON)


def _send_via_worker(subject: str, body: str) -> tuple:
    """POST to the mail worker. Returns (ok, error_message)."""
    url = CONFIG["mail_worker_url"].rstrip("/") + "/api/send"
    payload = json.dumps(
        {"to": CONFIG["report_email"], "subject": subject, "body": body}
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            # Cloudflare rejects python-urllib's default agent outright,
            # which looks exactly like this call is broken. Be explicit.
            "User-Agent": f"{CONFIG['site_name']}-site/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200, None
    except urllib.error.HTTPError as e:
        return False, f"mail worker returned {e.code}"
    except Exception as e:
        return False, str(e)[:120]


@router.post("/api/report")
def report(body: Report, request: Request):
    if not (0 <= body.x < GRID_SIZE and 0 <= body.y < GRID_SIZE):
        return JSONResponse({"ok": False, "error": "out of bounds"}, status_code=400)

    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    user = accounts.current_user(request)
    reason = body.reason.strip() or "(no reason given)"

    # stored first, so a confirmed report can be paid out later
    conn = db.db()
    conn.execute(
        "INSERT INTO reports (x, y, reason, ip, user_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            body.x,
            body.y,
            reason,
            ip,
            user["id"] if user else None,
            int(time.time()),        ),
    )
    conn.commit()
    conn.close()

    subject = f"{CONFIG['report_subject_prefix']} pixel {body.x},{body.y}"
    text = (
        f"A visitor reported the pixel at {body.x},{body.y} on the canvas.\n\n"
        f"Reason: {reason}\n"
        f"Reported from IP: {ip}\n"
        f"Account: {user['username'] if user else 'anonymous'}\n"
        f"Link: {str(request.base_url).rstrip('/')}#p{body.x}.{body.y}\n"
    )

    ok, err = _send_via_worker(subject, text)
    if not ok:
        return JSONResponse(
            {
                "ok": False,
                "error": "could not deliver the report",
                "detail": err,
                "fallback_email": CONFIG["report_email"],
            },
            status_code=502,
        )
    return {"ok": True, "reward_note": "if the owner agrees, this earns you pixels"}


feature(
    "report",
    router,
    title="Report a pixel",
    description="flag a pixel; it lands in the owner's inbox and can pay you credits.",
)
