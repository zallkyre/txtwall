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

## 🔒 How the encryption works

```
your browser ──encrypt (AES-GCM)──▶ ciphertext ──▶ server (SQLite)
your browser ◀──decrypt (AES-GCM)── ciphertext ◀── server
```

- **AES-256-GCM** via the browser's WebCrypto API — no crypto libraries shipped
- The shared key is derived from a constant string (`SHA-256`), so every visitor reads and writes the same wall
- The server stores **only ciphertext + IV** — message content never touches the disk in plaintext
- Messages **auto-delete after 24 hours** (configurable `TTL_SECONDS` in `app.py`)

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
| `/api/messages` | GET | — | Latest 200 messages: `[{id, ct, iv, created_at}]` |
| `/api/post` | POST | `{ct, iv}` (base64) | `{ok: true}` |

All ciphertext is base64-encoded AES-GCM output. The server never sees plaintext.

## 🚀 Deploy your own

### 1. App

```bash
ssh zallkyre@<pi-ip>
mkdir txtwall && cd txtwall
pip install fastapi uvicorn
# copy app.py + static/ from this repo
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

| File | Purpose |
|------|---------|
| `app.py` | FastAPI backend + SQLite |
| `static/index.html` | The wall — single page, no dependencies |
| `txtwall.service` | systemd unit for 24/7 running |
| `requirements.txt` | Python deps |

## 📜 License

MIT — do whatever you want with it.

<div align="center">

**Made with ❤️ and a Raspberry Pi**

</div>