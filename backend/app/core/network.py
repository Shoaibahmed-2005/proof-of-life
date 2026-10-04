"""
Which address should the phone use to reach this laptop?

The QR code carries the backend URL. On a laptop with several network
adapters (Wi-Fi, Ethernet, VPN, WSL/Hyper-V, VirtualBox, Docker) the address
that the default route uses is not always the Wi-Fi one, so:

  1. PUBLIC_BASE_URL in .env always wins (e.g. a cloudflared URL, or a fixed IP).
  2. Otherwise, on Windows, `ipconfig` is parsed and an adapter that has a
     default gateway and looks like Wi-Fi/Ethernet is preferred.
  3. Otherwise the address of the default route is used.

The choice (and every candidate) is printed at startup, with a warning when
there is more than one, so the operator can pin the right one.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

VIRTUAL_HINTS = ("vethernet", "wsl", "hyper-v", "virtualbox", "vmware", "docker", "vpn", "wireguard",
                 "tap", "tun", "loopback", "bluetooth", "zerotier", "tailscale", "npcap")
REAL_HINTS = ("wi-fi", "wifi", "wireless", "wlan", "ethernet")


@dataclass(frozen=True)
class Candidate:
    ip: str
    adapter: str = ""
    has_gateway: bool = False

    @property
    def looks_virtual(self) -> bool:
        name = self.adapter.lower()
        if any(h in name for h in VIRTUAL_HINTS):
            return True
        # Common default ranges of virtual adapters.
        return self.ip.startswith("192.168.56.") or self.ip.startswith("172.17.")

    @property
    def score(self) -> int:
        s = 0
        if self.has_gateway:
            s += 4
        if any(h in self.adapter.lower() for h in REAL_HINTS):
            s += 2
        if self.looks_virtual:
            s -= 5
        if self.ip.startswith("192.168."):
            s += 1
        return s


def _usable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.version == 4 and not addr.is_loopback and not addr.is_link_local and not addr.is_unspecified


def default_route_ip() -> str | None:
    """Address the OS would use for outside traffic (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            return ip if _usable(ip) else None
    except OSError:
        return None


def _parse_ipconfig(text: str) -> list[Candidate]:
    """Parses English `ipconfig` output into adapter/IPv4/gateway candidates."""
    out: list[Candidate] = []
    adapter, ips, gateway, in_gateway = "", [], False, False

    def flush():
        for ip in ips:
            out.append(Candidate(ip, adapter, gateway))

    for raw in text.splitlines():
        line = raw.rstrip()
        if line and not line.startswith(" ") and line.endswith(":"):
            flush()
            adapter, ips, gateway, in_gateway = line[:-1].strip(), [], False, False
            continue
        m = re.search(r"IPv4 Address[ .]*:\s*([\d.]+)", line)
        if m and _usable(m.group(1)):
            ips.append(m.group(1))
        if "Default Gateway" in line:
            in_gateway = True
            value = line.split(":", 1)[1].strip()
            gateway = gateway or bool(re.match(r"^\d+\.\d+\.\d+\.\d+$", value))
            continue
        if in_gateway:
            if re.match(r"^\s+\d+\.\d+\.\d+\.\d+\s*$", line):
                gateway = True  # IPv4 gateway on the line after an IPv6 one
            elif line.strip() and ":" in line and "." in line.split(":", 1)[0]:
                in_gateway = False
    flush()
    return out


def list_candidates() -> list[Candidate]:
    cands: list[Candidate] = []
    if sys.platform == "win32":
        try:
            text = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=5).stdout
            cands = _parse_ipconfig(text)
        except (OSError, subprocess.SubprocessError):
            cands = []
    if not cands:
        try:
            infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
            cands = [Candidate(ip) for ip in dict.fromkeys(i[4][0] for i in infos) if _usable(ip)]
        except OSError:
            cands = []
    route = default_route_ip()
    if route and route not in {c.ip for c in cands}:
        cands.append(Candidate(route, "default route", True))
    # Unique by IP, best first.
    seen, unique = set(), []
    for c in sorted(cands, key=lambda c: -c.score):
        if c.ip not in seen:
            seen.add(c.ip)
            unique.append(c)
    return unique


_cache: tuple[float, str | None, list[Candidate]] = (0.0, None, [])


def lan_ip(max_age_s: float = 60.0) -> str | None:
    """Best LAN address for phones on the same Wi-Fi (cached for a minute)."""
    global _cache
    now = time.monotonic()
    if now - _cache[0] > max_age_s:
        cands = list_candidates()
        best = cands[0].ip if cands else None
        _cache = (now, best, cands)
    return _cache[1]


def startup_report(port: int, public_base_url: str) -> str:
    """Human-readable summary printed when the backend starts."""
    cands = list_candidates()
    lines = ["", "=" * 72, "Proof of Life backend: how phones reach this laptop"]
    if public_base_url:
        lines.append(f"  QR codes use PUBLIC_BASE_URL = {public_base_url}  (from .env)")
    elif cands:
        lines.append(f"  QR codes use  http://{cands[0].ip}:{port}   (auto-detected)")
        lines.append(f"  Portal on other devices: http://{cands[0].ip}:5173")
    else:
        lines.append("  ! No network address found. Phones can only connect over USB (adb reverse).")
    if len(cands) > 1:
        lines.append(f"  ! {len(cands)} network adapters found. If phones can't connect, the wrong one may be chosen:")
        for c in cands:
            tag = "virtual/VPN?" if c.looks_virtual else ("has gateway" if c.has_gateway else "no gateway")
            lines.append(f"      {c.ip:<16} {c.adapter or '(unknown adapter)'}  [{tag}]")
        lines.append(f"    Pin the Wi-Fi one in backend/.env:  PUBLIC_BASE_URL=http://<wifi-ip>:{port}")
    lines.append(f"  Windows Firewall must allow inbound TCP {port} (see ANDROID_BUILD.md, 'Wi-Fi setup').")
    lines.append("=" * 72)
    return "\n".join(lines)
