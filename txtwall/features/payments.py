"""Stripe purchases. Written, tested, and switched off.

**Why this is off by default:** Stripe, PayPal, Patreon, Ko-fi and Gumroad
all require the account holder to be 18 or older. If you are under 18 you
cannot open one of these accounts yourself — a parent or guardian has to
be the account holder. That is not a workaround-able rule, so nothing
here is switched on until someone with the right age creates the account.

The point of writing it now is that it costs nothing to have ready. Set
``payments_enabled`` to true and add the two Stripe keys, and purchases
work with no other code change. Until then credits still arrive through
``/grant`` in Discord or by reporting abuse, which needs no processor at
all.

How it is kept honest:

* the signature is verified with HMAC against the **raw** request body —
  re-serialising the JSON first would change the bytes and break it
* the credit is only granted once, keyed on the Stripe event id
* a client can never choose an amount; it picks a pack id that the server
  looks up in ``credit_packs``
"""

import hashlib
import hmac
import json
import time
import urllib.parse
import urllib.request

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import db
from ..config import CONFIG
from . import feature

router = APIRouter()

API = "https://api.stripe.com/v1"


def _enabled() -> bool:
    return bool(
        CONFIG.get("payments_enabled")
        and CONFIG.get("stripe_secret_key")
        and CONFIG.get("stripe_webhook_secret")
    )


def _verify_signature(raw: bytes, header: str) -> bool:
    """Check Stripe-Signature: t=<unix>,v1=<hmac hex> over '<t>.<raw>'."""
    secret = CONFIG["stripe_webhook_secret"]
    if not secret or not header:
        return False

    stamp, signatures = None, []
    for part in header.split(","):
        key, _, value = part.partition("=")
        if key == "t":
            stamp = value
        elif key == "v1":
            signatures.append(value)
    if not stamp or not signatures:
        return False

    # reject replays of an old signed payload
    if abs(int(time.time()) - int(stamp)) > 300:
        return False

    expected = hmac.new(
        secret.encode(), f"{stamp}.".encode() + raw, hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


def _pack_for(pack_id: str) -> dict | None:
    for pack in CONFIG["credit_packs"]:
        if pack["id"] == pack_id:
            return pack
    return None


@router.get("/api/payments/options")
def options():
    """What could be bought. Empty until payments are switched on."""
    if not _enabled():
        return {"ok": True, "enabled": False, "packs": []}
    return {
        "ok": True,
        "enabled": True,
        "packs": [
            {**pack, "price": CONFIG["credit_prices"].get(pack["id"])}
            for pack in CONFIG["credit_packs"]
        ],
    }


class Checkout(BaseModel):
    pack_id: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=CONFIG["username_max"])


@router.post("/api/payments/checkout")
def checkout(body: Checkout, request: Request):
    """Create a Stripe Checkout session and hand back the redirect URL.

    The pack and the amount are resolved from config on this side, so the
    client cannot invent a price. Credentials and the pack id ride along
    in metadata and the webhook reads them back.
    """
    if not _enabled():
        return JSONResponse({"ok": False, "error": "payments are not enabled"}, status_code=503)

    pack = _pack_for(body.pack_id)
    price = CONFIG["credit_prices"].get(body.pack_id)
    if not pack or not price:
        return JSONResponse({"ok": False, "error": "no such pack"}, status_code=400)

    form = urllib.parse.urlencode(
        {
            "mode": "payment",
            "success_url": str(request.base_url).rstrip("/") + "/?paid=1",
            "cancel_url": str(request.base_url).rstrip("/") + "/?cancelled=1",
            "line_items[0][price_data][currency]": CONFIG.get("currency", "usd"),
            "line_items[0][price_data][unit_amount]": str(price),
            "line_items[0][price_data][product_data][name]": pack["label"],
            "line_items[0][quantity]": "1",
            "metadata[pack_id]": body.pack_id,
            "metadata[username]": body.username.strip(),
        }
    ).encode()
    req = urllib.request.Request(
        f"{API}/checkout/sessions",
        data=form,
        headers={
            "Authorization": f"Bearer {CONFIG['stripe_secret_key']}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "txtwall/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            session = json.loads(resp.read().decode())
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": "could not reach stripe", "detail": str(e)[:120]},
            status_code=502,
        )
    return {"ok": True, "url": session.get("url")}


@router.post("/api/payments/stripe")
async def stripe_webhook(request: Request):
    raw = await request.body()
    if not _enabled():
        return JSONResponse({"ok": False, "error": "payments are not enabled"}, status_code=503)
    if not _verify_signature(raw, request.headers.get("stripe-signature", "")):
        return JSONResponse({"ok": False, "error": "bad signature"}, status_code=400)

    try:
        event = json.loads(raw.decode())
    except ValueError:
        return JSONResponse({"ok": False, "error": "bad payload"}, status_code=400)

    # one-time events only, and only credits we can look up ourselves
    if event.get("type") not in ("checkout.session.completed", "payment_intent.succeeded"):
        return {"ok": True, "ignored": event.get("type")}

    obj = event.get("data", {}).get("object", {})
    event_id = str(event.get("id", ""))
    pack = _pack_for(str(obj.get("metadata", {}).get("pack_id", "")))
    username = str(obj.get("metadata", {}).get("username", ""))
    if not pack or not username:
        return {"ok": True, "ignored": "no pack"}

    conn = db.db()
    # the event id is the idempotency key, so a redelivery pays out once
    already = conn.execute(
        "SELECT 1 FROM credits WHERE source = 'stripe' AND ref = ?", (event_id,)
    ).fetchone()
    if already:
        conn.close()
        return {"ok": True, "duplicate": True}

    user = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if not user:
        conn.close()
        return {"ok": True, "ignored": "unknown username"}

    db.grant_credit(conn, user["id"], pack["pixels"], "purchase", "stripe", event_id)
    conn.commit()
    conn.close()
    return {"ok": True, "granted": pack["pixels"], "username": username}


feature(
    "payments",
    router,
    title="Buy pixels",
    description="stripe checkout for extra pixels. off until an 18+ account exists.",
)
