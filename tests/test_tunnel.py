import pytest
from devsnap.supervisor.tunnel import QuickTunnel, parse_tunnel_url_from_line


def test_parse_tunnel_url_plain_text():
    line = "2026-10-20T14:00:00Z INF |  https://orange-banana-1234.trycloudflare.com |"
    url = parse_tunnel_url_from_line(line)
    assert url == "https://orange-banana-1234.trycloudflare.com"


def test_parse_tunnel_url_json():
    json_line = '{"level":"info","time":"2026-10-20T14:00:00Z","message":"Your quick tunnel: https://cool-tiger-5678.trycloudflare.com ready"}'
    url = parse_tunnel_url_from_line(json_line)
    assert url == "https://cool-tiger-5678.trycloudflare.com"


def test_parse_tunnel_url_no_match():
    line = "Random startup log without url"
    assert parse_tunnel_url_from_line(line) is None


@pytest.mark.asyncio
async def test_quick_tunnel_mock():
    tunnel = QuickTunnel(port=8000, service_name="backend")
    url = await tunnel.start(timeout=5.0)
    assert "trycloudflare.com" in url
    assert tunnel.tunnel_url == url
    tunnel.stop()
