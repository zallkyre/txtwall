"""txtwall — a shared pixel canvas.

Entry point. Everything else lives in the ``txtwall/`` package:

    config.py     all tunables, one dict
    db.py         sqlite schema, daily allowances, credit balance
    identity.py   signed device cookie, so limits survive a reload
    security.py   rate limiting, client IP, response headers
    geo.py        network checks for signup
    accounts.py   password + session helpers
    features/     one file per feature, auto-loaded (see features/__init__.py)

Adding a feature = add one file. See features/__init__.py for the recipe.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from txtwall import config, db, features, identity, security

app = FastAPI(title="txtwall", docs_url=None, redoc_url=None)


@app.middleware("http")
async def prepare(request, call_next):
    """Hand every visitor a signed identity, then harden the response.

    Doing the cookie here rather than in one endpoint means no route can
    forget it — which is what keeps a reload from resetting someone's
    daily allowance.
    """
    response = await call_next(request)
    identity.ensure_device_cookie(request, response)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    # The canvas is live data and the JS/CSS are coupled to it. A cached
    # core.js from an older deploy leaves the page half-wired, so opt every
    # response out of browser and Cloudflare caching.
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response


features.load_all(app)

app.mount("/", StaticFiles(directory=str(config.BASE_DIR / "static"), html=True), name="static")
