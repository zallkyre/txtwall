"""Deciding whether a signup looks like a real person.

Being straight about what this can and cannot do: there is no reliable way
to tell a VPN from a home connection without a paid database. Every "free
VPN checker" is a blocklist guess. So this module does two honest things
and leaves the third to you:

1. **Blocks networks that are never residential** — RFC1918 private space,
   loopback, carrier NAT, and the ranges Cloudflare and the big clouds
   publish. Free, no API keys, catches scripted signups.
2. **Optionally calls a real VPN-detection API** if you set
   ``vpn_check_url``. Only ever called at signup, so the cost is a fraction
   of a cent per signup on a small site.
3. **Otherwise does nothing clever.** It is Turnstile, not this, that
   actually stops bots.

The per-IP-per-week limit in the accounts feature does more day-to-day work
than anything in this file.
"""

import ipaddress
import json
import urllib.request

from .config import CONFIG

_BLOCKERS = None


def _blockers():
    """Compiled CIDR list, built once."""
    global _BLOCKERS
    if _BLOCKERS is None:
        nets = []
        for cidr in CONFIG["blocked_cidrs"]:
            try:
                nets.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                continue
        _BLOCKERS = nets
    return _BLOCKERS


def _parse_ip(ip: str):
    try:
        return ipaddress.ip_address(ip)
    except ValueError:
        return None


def blocked_network(ip: str) -> bool:
    """True when the address is private, reserved, or on our blocklist."""
    addr = _parse_ip(ip)
    if addr is None:
        return True  # no usable address, do not let it through
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    if addr.version != 4:
        return True  # no IPv6 blocklist yet; fail closed on signup
    return any(addr in net for net in _blockers())


def external_proxy_check(ip: str) -> bool | None:
    """Ask the configured VPN API. Returns True/False, or None if unconfigured.

    The URL must contain ``{ip}``; the response is expected to be JSON with
    a ``proxy`` boolean. Anything unexpected is treated as "not a proxy" so
    a third-party outage never blocks real signups.
    """
    template = CONFIG.get("vpn_check_url") or ""
    if not template:
        return None
    url = template.replace("{ip}", ip)
    req = urllib.request.Request(url, headers={"User-Agent": "txtwall/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return None
    value = data.get("proxy")
    return bool(value) if isinstance(value, bool) else None


def check(ip: str, trusted: bool = False) -> tuple:
    """(allowed, reason). Used by the signup endpoint.

    ``trusted`` means the address came from a proxy header Cloudflare set
    rather than from the socket, so it is the real visitor and cannot be
    a private range. A direct loopback connection is local development and
    is let through; anything else private or reserved is refused.
    """
    if not trusted and blocked_network(ip):
        addr = _parse_ip(ip)
        # a local dev request is fine, a stray LAN peer is not
        if addr is None or not addr.is_loopback:
            return False, "signups are not accepted from this network"

    verdict = external_proxy_check(ip)
    if verdict:
        return False, "signups are not accepted through VPNs or proxies"
    return True, ""
