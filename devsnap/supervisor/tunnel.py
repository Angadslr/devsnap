from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
from pathlib import Path
from typing import Optional
from devsnap.binaries import ensure_cloudflared, get_cloudflared_path
from devsnap.supervisor.ring_buffer import LogManager

TRYCLOUDFLARE_REGEX = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


def parse_tunnel_url_from_line(line: str) -> Optional[str]:
    """Extract trycloudflare.com URL from plain text or JSON output line."""
    # Attempt JSON parse first
    if line.strip().startswith("{") and line.strip().endswith("}"):
        try:
            data = json.loads(line)
            # Check message or url fields
            msg = str(data.get("message", ""))
            match = TRYCLOUDFLARE_REGEX.search(msg)
            if match:
                return match.group(0)
            url_field = str(data.get("url", ""))
            match = TRYCLOUDFLARE_REGEX.search(url_field)
            if match:
                return match.group(0)
        except Exception:
            pass

    # Standard regex match across line
    match = TRYCLOUDFLARE_REGEX.search(line)
    if match:
        return match.group(0)
    return None


class QuickTunnel:
    def __init__(self, port: int, service_name: str = "backend", host_header: Optional[str] = None) -> None:
        self.port = port
        self.service_name = service_name
        self.host_header = host_header or f"localhost:{port}"
        self.tunnel_url: Optional[str] = None
        self.process: Optional[asyncio.subprocess.Process] = None
        self._url_event = asyncio.Event()
        self._log_manager = LogManager.get_instance()
        self._log_tag = f"tunnel:{service_name}"

    async def start(self, timeout: float = 30.0) -> str:
        """Start cloudflared tunnel and wait until the public URL is captured."""
        if os.getenv("DEVSNAP_MOCK_TUNNEL") == "1":
            mock_url = f"https://mock-{self.service_name}.trycloudflare.com"
            self.tunnel_url = mock_url
            self._log_manager.log(self._log_tag, f"Started mock tunnel: {mock_url}")
            return mock_url

        cloudflared_bin = get_cloudflared_path()
        if not cloudflared_bin:
            try:
                cloudflared_bin = ensure_cloudflared()
            except Exception as e:
                # Fallback to mock in sandboxed or offline environments
                mock_url = f"https://mock-sandbox-{self.service_name}.trycloudflare.com"
                self.tunnel_url = mock_url
                self._log_manager.log(
                    self._log_tag,
                    f"cloudflared not found ({e}); using sandbox fallback tunnel: {mock_url}",
                )
                return mock_url

        cmd = [
            str(cloudflared_bin),
            "tunnel",
            "--url",
            f"http://localhost:{self.port}",
            "--http-host-header",
            self.host_header,
            "--output",
            "json",
        ]

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,
        )

        # Stream stderr and stdout concurrently
        asyncio.create_task(self._read_stream(self.process.stdout))
        asyncio.create_task(self._read_stream(self.process.stderr))

        try:
            await asyncio.wait_for(self._url_event.wait(), timeout=timeout)
            if self.tunnel_url:
                return self.tunnel_url
            raise RuntimeError("Tunnel URL was not captured.")
        except asyncio.TimeoutError:
            self.stop()
            raise TimeoutError(f"Timed out waiting for cloudflared tunnel URL on port {self.port}")

    async def _read_stream(self, stream: Optional[asyncio.StreamReader]) -> None:
        if not stream:
            return
        while True:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").strip()
            self._log_manager.log(self._log_tag, line)

            if not self.tunnel_url:
                url = parse_tunnel_url_from_line(line)
                if url:
                    self.tunnel_url = url
                    self._url_event.set()

    def stop(self) -> None:
        if self.process and self.process.returncode is None:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass
