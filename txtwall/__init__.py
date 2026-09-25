"""txtwall backend package.

Module map:
    config.py    every tunable value, loaded from DEFAULTS + config.json
    db.py        sqlite schema, TTL purge, quota accounting
    security.py  rate limiting, client IP, response headers
    images.py    upload validation and re-encoding
    accounts.py  password hashing, rotating account numbers, sessions
    features/    one file per feature, discovered and mounted at startup
"""

__all__ = ["config", "db", "security", "images", "accounts", "features"]
