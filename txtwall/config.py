"""Site configuration.

Everything tunable lives in DEFAULTS below, so a developer can read the
whole behaviour of the site in one file.

To change a value without editing code, create ``config.json`` next to
``app.py`` and put only the keys you want to override in it::

    {
      "support_email": "owner@txtwall.xyz",
      "features": { "payments": false }
    }

``config.json`` is git-ignored on purpose. Secrets belong in the
environment as ``TXTWALL_<KEY>`` (uppercased), never in that file.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Values that must never be served to the browser.
PRIVATE_KEYS = frozenset(
    {
        "mail_worker_url",
        "admin_token",
        "turnstile_secret",
        "stripe_secret_key",
        "stripe_webhook_secret",
        "vpn_check_url",
    }
)


DEFAULTS = {
    # ---------------------------------------------------------- site
    "site_name": "txtwall",
    "tagline": "one pixel at a time.",
    "support_email": "owner@txtwall.xyz",
    "support_label": "email support",
    "footer_note": (
        "one shared canvas. nobody's pixels expire. 10 pixels a day "
        "anonymously, 100 with an account, more if you have credits."
    ),

    # --------------------------------------------------------- canvas
    "grid_size": 256,                       # 256x256 = 65,536 pixels
    "palette": [
        "#000000", "#141414", "#3d3d3d", "#666666",
        "#fcfcfc", "#7e2553", "#008751", "#5b2757",
        "#4a1c1c", "#a6382e", "#d0a30a", "#6f42c1",
        "#3684a4", "#4b6910", "#9b179b", "#eb8b0b",
    ],

    # ---------------------------------------------------- daily quotas
    # These reset at UTC midnight. Purchased credits sit on top and are
    # only spent once the free allowance is used up.
    "anon_pixel_daily": 10,                 # anonymous: pixels per day
    "user_pixel_daily": 100,                # account: pixels per day
    "pixel_cooldown": 30,                   # seconds between pixels
    "erase_costs_pixel": True,              # erasing spends quota too

    # ------------------------------------------------------- accounts
    "account_number_digits": 45,
    "session_days": 30,
    "username_min": 3,
    "username_max": 32,
    "password_min": 4,
    "password_max": 64,
    "device_cookie_days": 365,              # anonymous identity lifetime
    "signup_per_week": 1,                   # accounts per IP per 7 days

    # ------------------------------------------------------ anti-abuse
    # Cloudflare Turnstile. Free, and far more effective at stopping
    # scripted signups than any IP check. Leave required=false until the
    # keys are filled in, or nobody can sign up at all.
    "turnstile_required": False,
    "turnstile_site_key": "",
    "turnstile_secret": "",
    # Optional external VPN/proxy check, called only at signup. Format:
    #   "<url>?ip={ip}"  -> JSON containing {"proxy": true|false}
    # Left blank, signup uses the built-in datacenter blocklist only.
    "vpn_check_url": "",
    # Networks that are never real visitors. Extend as you see abuse.
    "blocked_cidrs": [
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
        "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24", "192.168.0.0/16",
        "198.18.0.0/15", "224.0.0.0/4", "240.0.0.0/4",
    ],

    # -------------------------------------------------- rate limiting
    "rate_limit": 30,                       # actions per window per IP
    "rate_window": 10,                      # window in seconds

    # -------------------------------------------------------- credits
    # Pixels bought or earned. Never expire. Only spent after the daily
    # free allowance is used up.
    "credit_packs": [
        {"id": "pack_100", "pixels": 100, "label": "100 pixels"},
        {"id": "pack_500", "pixels": 500, "label": "500 pixels"},
        {"id": "pack_2000", "pixels": 2000, "label": "2000 pixels"},
    ],
    "credit_prices": {"pack_100": 100, "pack_500": 500, "pack_2000": 2000},
    "credit_reward_per_report": 25,         # for a report the owner confirms

    # ------------------------------------------------------- payments
    # Stripe is wired up but OFF by default. Payment processors require an
    # 18+ account holder, so this stays off until a parent/guardian sets
    # one up. Everything else (credits, grants) works without it.
    "payments_enabled": False,
    "stripe_secret_key": "",
    "stripe_webhook_secret": "",

    # ---------------------------------------------------------- admin
    # Bearer token for /api/admin/*, used by the Discord bot's /grant.
    "admin_token": "",

    # ---------------------------------------------------------- mail
    "mail_worker_url": "https://mail.txtwall.xyz",
    "report_email": "owner@txtwall.xyz",
    "report_subject_prefix": "[txtwall report]",

    # -------------------------------------------------------- features
    # flip a feature off here (or in config.json) and its routes stop
    # loading and its front-end module stops mounting.
    "features": {
        "canvas": True,
        "accounts": True,
        "credits": True,
        "support_panel": True,
        "report": True,
        "payments": False,
    },
}


def _coerce(default, text):
    """Turn an environment string into the type of the default value."""
    if isinstance(default, bool):
        return text.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(text)
    if isinstance(default, float):
        return float(text)
    if isinstance(default, list):
        try:
            return json.loads(text)
        except ValueError:
            return default
    return text


def _load() -> dict:
    cfg = json.loads(json.dumps(DEFAULTS))  # deep copy

    path = BASE_DIR / "config.json"
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")))

    for key, default in DEFAULTS.items():
        env = os.environ.get("TXTWALL_" + key.upper())
        if env is not None:
            try:
                cfg[key] = _coerce(default, env)
            except (TypeError, ValueError):
                pass
    return cfg


CONFIG = _load()

# convenience accessors used all over the code
DB_PATH = Path(os.environ.get("TXTWALL_DB", str(BASE_DIR / "txtwall.db")))

PALETTE = [c.lower() for c in CONFIG["palette"]]
GRID_SIZE = int(CONFIG["grid_size"])


def feature_on(name: str) -> bool:
    """Is a feature enabled? Checked by the registry before mounting."""
    return bool(CONFIG.get("features", {}).get(name, True))


def public_config() -> dict:
    """The slice of config the browser is allowed to see."""
    return {
        "site_name": CONFIG["site_name"],
        "tagline": CONFIG["tagline"],
        "support_email": CONFIG["support_email"],
        "support_label": CONFIG["support_label"],
        "footer_note": CONFIG["footer_note"],
        "grid_size": GRID_SIZE,
        "palette": PALETTE,
        "cooldown": CONFIG["pixel_cooldown"],
        "erase_costs_pixel": CONFIG["erase_costs_pixel"],
        "signup_per_week": CONFIG["signup_per_week"],
        "turnstile_site_key": CONFIG["turnstile_site_key"] if CONFIG["turnstile_required"] else "",
        "payments_enabled": bool(CONFIG["payments_enabled"]),
        "credit_packs": CONFIG["credit_packs"] if CONFIG["payments_enabled"] else [],
        "features": CONFIG["features"],
        "limits": {
            "anon": CONFIG["anon_pixel_daily"],
            "user": CONFIG["user_pixel_daily"],
        },
    }
