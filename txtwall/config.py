"""Site configuration.

Everything tunable lives in DEFAULTS below, so a developer can read the
whole behaviour of the site in one file.

To change a value without editing code, create ``config.json`` next to
``app.py`` and put only the keys you want to override in it::

    {
      "support_email": "owner@txtwall.xyz",
      "features": { "report": false }
    }

``config.json`` is git-ignored on purpose. Secrets belong in the
environment as ``TXTWALL_<KEY>`` (uppercased), never in that file.
"""

import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Values that must never be served to the browser.
PRIVATE_KEYS = frozenset({"mail_worker_url"})


DEFAULTS = {
    # ---------------------------------------------------------- site
    "site_name": "txtwall",
    "tagline": "encrypted. anonymous. optional accounts.",
    "support_email": "owner@txtwall.xyz",
    "support_label": "email support",
    "footer_note": (
        "messages are encrypted in your browser. the server only stores "
        "ciphertext. images are re-encoded and scaled to 1080x1080. "
        "messages auto-delete after 24h."
    ),

    # -------------------------------------------------------- messages
    "ttl_seconds": 24 * 3600,            # messages auto-delete after 24h
    "max_ct_len": 5000,                  # ciphertext length cap
    "max_iv_len": 64,                    # IV length cap
    "max_rows": 5000,                    # hard cap on stored messages

    # -------------------------------------------------- rate limiting
    # per IP, POST only
    "rate_limit": 5,                     # actions allowed per window
    "rate_window": 10,                   # window in seconds

    # ---------------------------------------------------- daily quotas
    "anon_msg_daily": 5,                 # anonymous: messages per day
    "anon_img_daily": 1,                 # anonymous: images per day
    "user_msg_daily": 250,               # account: messages per day
    "user_img_daily": 50,                # account: images per day

    # -------------------------------------------------------- accounts
    "account_number_digits": 45,         # account number length (32-64)
    "session_days": 30,                  # session lifetime
    "username_min": 3,
    "username_max": 32,
    "password_min": 4,
    "password_max": 64,

    # ---------------------------------------------------------- images
    "max_image_bytes": 5 * 1024 * 1024,  # max upload size (5MB)
    "image_max_dim": 1080,               # images scaled to fit this box
    "uploads_dir": "uploads",            # where images are stored

    # ------------------------------------------ storage-aware shrinking
    # as the disk fills, daily caps shrink. gentle curve:
    #   < 50% used  -> full caps
    #   50-70%      -> 80% of caps
    #   70-85%      -> 60% of caps
    #   85-95%      -> 40% of caps
    #   > 95%       -> 20% of caps (never 0, blocks nothing entirely)
    "cap_shrink": [
        [0.50, 1.00],
        [0.70, 0.80],
        [0.85, 0.60],
        [0.95, 0.40],
        [1.01, 0.20],
    ],

    # -------------------------------------------------------- features
    # flip a feature off here (or in config.json) and its routes stop
    # loading and its front-end module stops mounting.
    "features": {
        "wall": True,
        "images": True,
        "reactions": True,
        "random_message": True,
        "live_viewers": True,
        "accounts": True,
        "search": True,
        "support_panel": True,
        "report": True,
    },

    # --------------------------------------------------------- reports
    # "report" emails the site owner through the Cloudflare mail worker.
    # The worker decides auto-reply vs. human escalation.
    "mail_worker_url": "https://mail.txtwall.xyz",
    "report_email": "owner@txtwall.xyz",
    "report_subject_prefix": "[txtwall report]",
}


def _coerce(default, text):
    """Turn an environment string into the type of the default value."""
    if isinstance(default, bool):
        return text.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(text)
    if isinstance(default, float):
        return float(text)
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
UPLOADS = Path(CONFIG["uploads_dir"])
if not UPLOADS.is_absolute():
    UPLOADS = BASE_DIR / UPLOADS


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
        "max_text_len": 500,
        "max_image_bytes": CONFIG["max_image_bytes"],
        "features": CONFIG["features"],
        "limits": {
            "anon": {
                "messages": CONFIG["anon_msg_daily"],
                "images": CONFIG["anon_img_daily"],
            },
            "user": {
                "messages": CONFIG["user_msg_daily"],
                "images": CONFIG["user_img_daily"],
            },
        },
    }
