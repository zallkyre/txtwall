"""Reporting a message to the site owner.

The visitor never sees an email form. They type a reason, the server
forwards it to the Cloudflare mail worker, and the worker decides whether
Groq can answer automatically or a human gets pinged on Discord.

The recipient is fixed in config (``report_email``). A client can never
choose where mail goes, so this endpoint cannot be used as a relay.
"""

import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import security
from ..config import CONFIG
from . import feature

router = APIRouter()

MAX_REASON = 500


class Report(BaseModel):
    message_id: int = Field(ge=1)
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
    ip = security.client_ip(request)
    if security.rate_limited(ip):
        return security.too_many()

    reason = body.reason.strip() or "(no reason given)"
    subject = f"{CONFIG['report_subject_prefix']} message #{body.message_id}"
    text = (
        f"A visitor reported message #{body.message_id} on the wall.\n\n"
        f"Reason: {reason}\n"
        f"Reported from IP: {ip}\n"
        f"Link: {str(request.base_url).rstrip('/')}#m{body.message_id}\n"
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
    return {"ok": True}


feature(
    "report",
    router,
    title="Report a message",
    description="visitors can flag a message; it lands in the owner's inbox and Discord.",
)
