<div align="center">

# 🔐 txtwall

**An encrypted, anonymous text wall. No accounts. No tracking.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)](https://www.sqlite.org/)
[![Cloudflare Tunnel](https://img.shields.io/badge/Cloudflare%20Tunnel-live-F38020.svg)](https://txtwall.xyz)

**Live at [txtwall.xyz](https://txtwall.xyz)** — running 24/7 on a Raspberry Pi 3

</div>

---

## ✨ What it is

A public wall where anyone can post a message. No signup, no login, no cookies, no tracking. Messages are **encrypted in your browser** before they ever leave it — the server only ever stores ciphertext.

- Post text and images, react with emoji, search what's loaded
- Optional accounts if you want higher daily limits
- Report any message straight to the owner's inbox
- Everything vanishes after 24 hours. Accounts are kept forever.

## 🔒 How the encryption works

```
your browser ──encrypt (AES-GCM)──▶ ciphertext ──▶ server (SQLite)
your browser ◀──decrypt (AES-GCM)── ciphertext ◀── server
```

- **AES-256-GCM** via the browser's WebCrypto API — no crypto libraries shipped
- The shared key is derived from a constant string (`SHA-256`), so every visitor reads and writes the same wall
- The server stores **only ciphertext + IV** — message content never touches the disk in plaintext
- Messages **auto-delete after 24 hours** (set `ttl_seconds` in `txtwall/config.py`)

> **Honest note:** because the wall is shared, the key lives in the page's JavaScript. This is *encryption at rest* (the server can't read messages without pulling the key from the code), not end-to-end secrecy. For a public anonymous wall, that's the right tradeoff.

## 🛠️ Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | FastAPI + Uvicorn | Tiny, async, zero config |
| Storage | SQLite | One file, no server, survives reboots |
| Frontend | Vanilla HTML/JS | No frameworks, no build step |
| Exposure | Cloudflare Tunnel | No open ports, DDoS protection, free HTTPS |
| Host | Raspberry Pi 3 | 1 GB RAM, ~40 MB used by the app |

## 📡 API

| Endpoint | Method | Body | Returns |
|----------|--------|------|---------|
| `/api/config` | GET | — | Site name, support address, feature flags, limits |
| `/api/stats` | GET | — | Message and account counts |
| `/api/messages` | GET | — | Latest 200 messages + live viewer count |
| `/api/messages/random` | GET | — | One random message |
| `/api/post` | POST | `{ct, iv}` (base64) | `{ok: true}` |
| `/api/post/image` | POST | raw image bytes | `{ok, image}` |
| `/api/react` | POST | `{message_id, emoji}` | `{ok: true}` |
| `/api/report` | POST | `{message_id, reason}` | `{ok: true}` — emails the owner |
| `/api/signup` / `/api/login` / `/api/logout` | POST | `{username, password}` | Session cookie + account number |
| `/api/me` | GET | — | Current user and quota usage |
| `/api/account/permanent` | POST | `{permanent}` | Keeps the account number fixed |

All ciphertext is base64-encoded AES-GCM output. The server never sees plaintext.

## 🧩 Adding a feature

Every feature is one file. Nothing else needs editing.

**Backend** — drop a module in `txtwall/features/`:

```python
# txtwall/features/polls.py
from fastapi import APIRouter
from . import feature

router = APIRouter()

@router.get("/api/polls")
def active_polls():
    return {"polls": []}

feature("polls", router, title="Polls", description="let people vote")
```

It is imported and mounted automatically. Turn it on in `config.json`
(or leave the key out — a feature is on unless switched off):

```json
{ "features": { "polls": true } }
```

**Frontend** — drop a module in `static/js/features/` and add one
`<script>` tag to `index.html`:

```javascript
TW.feature('polls', {
  title: 'Polls',
  mount() {
    TW.api('/api/polls').then((d) => console.log(d.polls));
  }
});
```

`mount()` runs once, after `GET /api/config` resolves, and only if the
server says the feature is on. If your feature decorates each message,
register `TW.onRender((wall) => { ... })` instead of touching the DOM
yourself — it runs after every wall refresh.

**Settings** — copy `config.example.json` to `config.json` and override
only what you need. Secrets go in `TXTWALL_*` environment variables, never
in that file.

## 🚀 Deploy your own

### 1. App

```bash
ssh zallkyre@<pi-ip>
mkdir txtwall && cd txtwall
pip install fastapi uvicorn pillow
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

# create a tunnel in the Cloudflare dashboard, then:
sudo cloudflared service install <tunnel-token>
```

Point a DNS CNAME at your tunnel (`<tunnel-id>.cfargotunnel.com`, proxied) and you're live.

## 📁 Files

| Path | Purpose |
|------|---------|
| `app.py` | Entry point — mounts features and static files |
| `txtwall/config.py` | Every tunable value, in one dict |
| `txtwall/db.py` | SQLite schema, TTL purge, quota accounting |
| `txtwall/security.py` | Rate limiting, client IP, response headers |
| `txtwall/images.py` | Upload validation and re-encoding |
| `txtwall/accounts.py` | Passwords, rotating account numbers, sessions |
| `txtwall/features/` | One file per feature, auto-loaded |
| `static/index.html` | Page shell |
| `static/css/app.css` | Styles |
| `static/js/core.js` | Shared helpers, encryption, fetch wrapper |
| `static/js/features/` | One file per front-end feature |
| `config.example.json` | Copy to `config.json` to override settings |
| `txtwall.service` | systemd unit for 24/7 running |
| `requirements.txt` | Python deps |

## 📜 License

MIT — do whatever you want with it.

<div align="center">

**Made with ❤️ and a Raspberry Pi**

</div>