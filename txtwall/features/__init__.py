"""Feature registry.

A feature is a module in this folder. It builds an ``APIRouter``, then
hands it to :func:`feature`. At startup every module here is imported
automatically and its router is mounted — so adding a feature never
requires editing ``app.py``.

To add one::

    # txtwall/features/polls.py
    from fastapi import APIRouter
    from . import feature

    router = APIRouter()

    @router.get("/api/polls")
    def active_polls():
        return {"polls": []}

    feature("polls", router, title="Polls", description="let people vote")

Then turn it on in ``config.json``::

    { "features": { "polls": true } }

Front-end features work the same way: drop a file in
``static/js/features/``, call ``TW.feature(...)``, and it mounts itself
once the site config has loaded.
"""

import importlib
import pkgutil
from pathlib import Path

from ..config import feature_on

REGISTRY: list = []


def feature(name: str, router, **meta) -> None:
    """Register a router. `name` must match a key in CONFIG['features']."""
    REGISTRY.append({"name": name, "router": router, **meta})


def load_all(app) -> list:
    """Import every feature module and mount the enabled ones."""
    pkg_dir = Path(__file__).parent
    modules = sorted(m.name for m in pkgutil.iter_modules([str(pkg_dir)]))

    for mod_name in modules:
        if mod_name.startswith("_"):
            continue
        importlib.import_module(f"{__package__}.{mod_name}")

    mounted, skipped = [], []
    for entry in REGISTRY:
        if feature_on(entry["name"]):
            app.include_router(entry["router"])
            mounted.append(entry["name"])
        else:
            skipped.append(entry["name"])
    return {"mounted": mounted, "skipped": skipped, "modules": modules}
