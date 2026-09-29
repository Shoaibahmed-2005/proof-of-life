"""Wi-Fi reachability: adapter selection for the QR address, LAN CORS."""

from app.core import network

IPCONFIG = """
Windows IP Configuration


Ethernet adapter vEthernet (WSL (Hyper-V firewall)):

   Connection-specific DNS Suffix  . :
   IPv4 Address. . . . . . . . . . . : 172.29.160.1
   Subnet Mask . . . . . . . . . . . : 255.255.240.0
   Default Gateway . . . . . . . . . :

Ethernet adapter VirtualBox Host-Only Network:

   IPv4 Address. . . . . . . . . . . : 192.168.56.1
   Default Gateway . . . . . . . . . :

Unknown adapter WireGuard Tunnel:

   IPv4 Address. . . . . . . . . . . : 10.66.66.2
   Default Gateway . . . . . . . . . :

Wireless LAN adapter Wi-Fi:

   IPv4 Address. . . . . . . . . . . : 192.168.1.10
   Subnet Mask . . . . . . . . . . . : 255.255.255.0
   Default Gateway . . . . . . . . . : fe80::1%12
                                       192.168.1.1
"""


def test_ipconfig_prefers_wifi_with_gateway_over_virtual_adapters():
    cands = sorted(network._parse_ipconfig(IPCONFIG), key=lambda c: -c.score)
    assert cands[0].ip == "192.168.1.10" and cands[0].has_gateway
    by_ip = {c.ip: c for c in cands}
    assert by_ip["172.29.160.1"].looks_virtual
    assert by_ip["192.168.56.1"].looks_virtual
    assert by_ip["10.66.66.2"].looks_virtual
    assert not by_ip["192.168.1.1" if "192.168.1.1" in by_ip else "192.168.1.10"].looks_virtual


def test_startup_report_warns_on_multiple_adapters(monkeypatch):
    monkeypatch.setattr(network, "list_candidates",
                        lambda: sorted(network._parse_ipconfig(IPCONFIG), key=lambda c: -c.score))
    report = network.startup_report(8000, "")
    assert "http://192.168.1.10:8000" in report
    assert "4 network adapters found" in report and "PUBLIC_BASE_URL" in report
    pinned = network.startup_report(8000, "https://demo.trycloudflare.com")
    assert "PUBLIC_BASE_URL = https://demo.trycloudflare.com" in pinned


def test_public_base_url_overrides_qr_address(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "http://10.1.2.3:8000/")
    assert client.post("/api/v1/sessions").json()["qr_payload"]["base_url"] == "http://10.1.2.3:8000"


def test_auto_address_replaces_localhost_with_lan_ip(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")
    monkeypatch.setattr(network, "lan_ip", lambda *a, **k: "192.168.1.10")
    qr = client.post("/api/v1/sessions", headers={"host": "localhost:8000"}).json()["qr_payload"]
    assert qr["base_url"] == "http://192.168.1.10:8000"


def test_cors_allows_portal_opened_from_lan(client):
    r = client.options("/api/v1/sessions", headers={
        "Origin": "http://192.168.1.10:5173", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://192.168.1.10:5173"
    r = client.options("/api/v1/sessions", headers={
        "Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
