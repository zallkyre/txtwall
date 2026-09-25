<div align="center">

# 🎨 txtwall

**One shared pixel canvas. Nothing expires.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)](https://www.sqlite.org/)
[![Cloudflare Tunnel](https://img.shields.io/badge/Cloudflare%20Tunnel-live-F38020.svg)](https://txtwall.xyz)

**Live at [txtwall.xyz](https://txtwall.xyz)** — running 24/7 on a Raspberry Pi 3

</div>

---

## ✨ What it is

A 256×256 grid of 65,536 cells that anyone can paint. There is no feed to
scroll and nothing to write — one pixel, one go.

- **10 pixels a day** anonymously, **100 a day** with an account
- **Nothing ever expires.** Pixels stay until the owner wipes the canvas
- **16 fixed colours.** A palette keeps it legible; free colour turns art to mud
- **30 second cooldown** between pixels, so nobody dumps a quota in two minutes
- Buying or earning pixels adds to today's allowance on top

## 🔒 How the limits actually hold

The interesting problem here is not the canvas, it is stopping someone
getting free pixels by refreshing the page. Nothing that decides a limit
lives in the browser:

1. **Signed device cookie.** Every visitor gets a random id plus an HMAC
   the client cannot forge or edit. Reloading keeps the same id, so the
   counter does not reset. See `txtwall/identity.py`.
2. **Counters are rows.** `pixel_usage` is keyed by (UTC day, identity) and
   incremented inside a transaction. A server restart changes nothing.
3. **Accounts win outright.** A signed-in user is keyed by their user id,
   so the allowance follows them between devices.
4. **A per-IP brake** catches cookie-wiping from the same connection.

**The honest limitation:** clearing cookies or switching to a VPN gives you
a fresh identity. This raises the cost of abuse from trivial to "some
effort", which is the right bar for a canvas, and it is not a security
boundary against someone who is deliberately trying.

## 🪙 Pixels and credits

```
allowed today = daily base + unused credits
```

The free allowance resets at UTC midnight. Credits are a **separate pool**,
only spent once the free allowance is gone. So a purchase of 500 gives:

| Day | Free | Credits left | Total |
|---|---|---|---|
| 1 | 100 | 500 | 600 |
| 2 | 100 | 400 | 500 |
| … | 100 | ↓ | ↓ |
| 6 | 100 | 0 | 100 |

Credits never expire, and they are tied to the **account**, not the
browser, so a purchase cannot be lost by clearing cookies.

**Two ways to get them today**, neither needing a payment processor:

- **Ask the owner.** `/grant username 500` in Discord calls
  `POST /api/admin/grant` with a shared token.
- **Report abuse.** A report the owner marks valid pays the reporter.

Stripe checkout is written and tested in `txtwall/features/payments.py` but
**disabled**. Payment processors require an 18+ account holder; turn it on
with `payments_enabled` plus the two Stripe keys when that exists.

## 🛡️ Keeping signups honest

A free account is worth 10× an anonymous one, which is exactly the gap a
bot would farm. Three things stand in the way:

| Layer | Cost | What it stops |
|---|---|---|
| **Cloudflare Turnstile** | free | scripted signups — the layer that does the real work |
| **One account per IP per week** | free | casual repeat signups |
| **Network check** | free / optional | datacenters, and VPNs if you pay for an API |

Turnstile is off until you paste in your keys (`turnstile_required`).
Be aware this is friction, not proof: it raises the cost of mass signup,
it does not prevent a determined person.

## 🛠️ Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | FastAPI + Uvicorn | Tiny, async, zero config |
| Storage | SQLite | One file, no server, survives reboots |
| Frontend | Vanilla HTML/JS | No frameworks, no build step |
| Live updates | Polling an event cursor | Survives restarts, nothing to babysit |
| Exposure | Cloudflare Tunnel | No open ports, DDoS protection, free HTTPS |
| Host | Raspberry Pi 3 | 1 GB RAM, ~40 MB used by the app |

## 📡 API

| Endpoint | Method | Body | Returns |
|----------|--------|------|---------|
| `/api/config` | GET | — | Grid size, palette, limits, feature flags |
| `/api/stats` | GET | — | Cells painted, accounts, open reports |
| `/api/canvas` | GET | `?since=<cursor>` | Full canvas, or just the changes |
| `/api/pixel` | POST | `{x, y, color}` | Places one pixel, returns new allowance |
| `/api/pixel/erase` | POST | `{x, y}` | Clears a cell, costs a pixel |
| `/api/signup` / `/api/login` / `/api/logout` | POST | `{username, password}` | Session cookie |
| `/api/me` | GET | — | Current user and today's allowance |
| `/api/credits` | GET | — | Balance and ledger |
| `/api/admin/grant` | POST | `{username, pixels}` | **Bearer token.** Called by the Discord bot |
| `/api/admin/reports` | GET | — | **Bearer token.** Open reports |
| `/api/admin/resolve-report` | POST | `{report_id, valid, reward}` | **Bearer token.** Pays the reporter |
| `/api/payments/*` | — | — | Mounted only when payments are enabled |

## 🚀 Deploy your own

### 1. App

```bash
ssh zallkyre@<pi-ip>
mkdir txtwall && cd txtwall
pip install fastapi uvicorn
# copy app.py, txtwall/ and static/ from this repo
```

### 2. Run it forever

```bash
sudo cp txtwall.service /etc/systemd/system/
sudo systemctl enable --now txtwall
```

### 3. Expose it (Cloudflare Tunnel)

```bash
# install cloudflared (arm64)
curl -sL -o /tmp/cloudflared https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
sudo install -m 755 /tmp/cloudflared /usr/local/bin/cloudflared
sudo cloudflared service install <tunnel-token>
```

Point a DNS CNAME at your tunnel (`<tunnel-id>.cfargotunnel.com`, proxied)
and you're live.

> **The tunnel sets the client IP.** The app is bound to `127.0.0.1`, so
> every request arrives from loopback. `security.client_ip` therefore reads
> `CF-Connecting-IP` and friends — without that, the whole internet shares
> one daily allowance.

## 🧩 Adding a feature

Every feature is one file. Nothing else needs editing.

**Backend** — drop a module in `txtwall/features/`:

```python
# txtwall/features/heatmap.py
from fastapi import APIRouter
from . import feature

router = APIRouter()

@router.get("/api/heatmap")
def heatmap():
    return {"cells": []}

feature("heatmap", router, title="Heatmap", description="where the pixels land")
```

It is imported and mounted automatically. Switch it off in `config.json`:

```json
{ "features": { "heatmap": false } }
```

**Frontend** — drop a module in `static/js/features/` and add one
`<script>` tag to `index.html`:

```javascript
TW.feature('heatmap', {
  title: 'Heatmap',
  mount() {
    TW.api('/api/heatmap').then((d) => console.log(d.cells));
  }
});
```

`mount()` runs once, after `GET /api/config` resolves, and only if the
server says the feature is on. If your feature repaints the board, call
`TW.paintMeter(state)` with the `state` every endpoint returns, and update
`TW.state.pixels` then `schedule()` a redraw — never touch the canvas
directly.

**Settings** — copy `config.example.json` to `config.json` and override
only what you need. Secrets go in `TXTWALL_*` environment variables, never
in that file.

## 📁 Files

| Path | Purpose |
|------|---------|
| `app.py` | Entry point — middleware, feature load, static mount |
| `txtwall/config.py` | Every tunable value, in one dict |
| `txtwall/db.py` | Schema, daily allowances, credit balance |
| `txtwall/identity.py` | Signed device cookie — why reloads do not reset you |
| `txtwall/security.py` | Client IP, rate limiting, response headers |
| `txtwall/geo.py` | Network checks for signup |
| `txtwall/accounts.py` | Passwords, rotating account numbers, sessions |
| `txtwall/features/` | One file per feature, auto-loaded |
| `static/index.html` | Page shell |
| `static/css/app.css` | Styles |
| `static/js/core.js` | Shared helpers, fetch wrapper, allowance meter |
| `static/js/features/` | One file per front-end feature |
| `config.example.json` | Copy to `config.json` to override settings |
| `txtwall.service` | systemd unit for 24/7 running |
| `requirements.txt` | Python deps |

## 📜 License

MIT — do whatever you want with it.

<div align="center">

**Made with a Raspberry Pi**

</div>
