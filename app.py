"""txtwall — anonymous encrypted message wall.

Entry point. Everything else lives in the ``txtwall/`` package:

    config.py     all tunables, one dict
    db.py         sqlite schema, retention, quotas
    security.py   rate limiting, client IP, response headers
    images.py     upload validation
    accounts.py   password + session helpers
    features/     one file per feature, auto-loaded (see features/__init__.py)

Adding a feature = add one file. See features/__init__.py for the recipe.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from txtwall import config, db, features, security

config.UPLOADS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="txtwall", docs_url=None, redoc_url=None)
app.middleware("http")(security.security_headers)

features.load_all(app)

app.mount("/uploads", StaticFiles(directory=str(config.UPLOADS)), name="uploads")
app.mount("/", StaticFiles(directory=str(config.BASE_DIR / "static"), html=True), name="static")
