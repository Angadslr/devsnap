from __future__ import annotations

import asyncio
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from rich.console import Console
from rich.theme import Theme

from devsnap.config import DevSnapConfig, ServiceConfig
from devsnap.supervisor.env_injector import resolve_environment_variables
from devsnap.supervisor.ring_buffer import LogManager
from devsnap.supervisor.tunnel import QuickTunnel

CUSTOM_THEME = Theme({
    "backend": "cyan",
    "mobile": "magenta",
    "frontend": "blue",
    "tunnel": "green",
    "emulator": "yellow",
    "error": "bold red",
})

SERVICE_COLORS = ["cyan", "magenta", "blue", "green", "yellow", "bright_blue", "bright_magenta"]


class ManagedService:
    def __init__(self, name: str, config: ServiceConfig, root: Path, color: str = "cyan") -> None:
        self.name = name
        self.config = config
        self.root = root
        self.color = color
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False

    async def start(self, env: Dict[str, str], console: Console, log_manager: LogManager) -> None:
        cwd = (self.root / self.config.cwd).resolve() if self.config.cwd else self.root
        console.print(f"[{self.color}][{self.name}][/{self.color}] Booting: {self.config.cmd} (cwd: {cwd})")

        self.process = await asyncio.create_subprocess_shell(
            self.config.cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        self.is_running = True

        asyncio.create_task(self._stream_output(self.process.stdout, console, log_manager, is_err=False))
        asyncio.create_task(self._stream_output(self.process.stderr, console, log_manager, is_err=True))

    async def _stream_output(
        self,
        stream: Optional[asyncio.StreamReader],
        console: Console,
        log_manager: LogManager,
        is_err: bool = False,
    ) -> None:
        if not stream:
            return
        while True:
            line_bytes = await stream.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace").rstrip("\r\n")
            log_manager.log(self.name, line)
            timestamp = datetime.now().strftime("%H:%M:%S")
            style = "bold red" if is_err and "error" in line.lower() else self.color
            console.print(f"[dim]{timestamp}[/dim] [{style}][{self.name}][/{style}] {line}")

    def stop(self) -> None:
        self.is_running = False
        if self.process and self.process.returncode is None:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass


class ProcessSupervisor:
    _instance: Optional[ProcessSupervisor] = None

    def __init__(self, config: DevSnapConfig, root: Path, share: bool = False) -> None:
        self.config = config
        self.root = root
        self.share = share
        self.console = Console(theme=CUSTOM_THEME)
        self.log_manager = LogManager.get_instance()
        self.services: Dict[str, ManagedService] = {}
        self.tunnels: Dict[str, QuickTunnel] = {}
        self.tunnel_urls: Dict[str, str] = {}
        self._stop_event = asyncio.Event()
        ProcessSupervisor._instance = self

    @classmethod
    def get_instance(cls) -> Optional[ProcessSupervisor]:
        return cls._instance

    async def start(self) -> None:
        self.console.rule("[bold cyan]DevSnap Process Supervisor Booting[/bold cyan]")

        # 1. Initialize services
        for idx, (name, svc_cfg) in enumerate(self.config.services.items()):
            color = SERVICE_COLORS[idx % len(SERVICE_COLORS)]
            self.services[name] = ManagedService(name=name, config=svc_cfg, root=self.root, color=color)

        # 2. Boot background state / emulators if needed
        if self.config.state.firebase_emulators:
            fb_import = self.root / ".devsnap" / "state" / "firebase"
            import_flag = f" --import={fb_import}" if fb_import.is_dir() else ""
            self.console.print(f"[yellow][firebase][/yellow] Starting Firebase Emulators{import_flag}...")

        # 3. Start services that provide tunnels (e.g. backend)
        backend_svcs = [
            (name, svc) for name, svc in self.services.items()
            if svc.config.tunnel or (self.share and svc.config.port)
        ]
        other_svcs = [
            (name, svc) for name, svc in self.services.items()
            if (name, svc) not in backend_svcs
        ]

        # Boot backend services first
        for name, svc in backend_svcs:
            env = resolve_environment_variables(svc.config, self.tunnel_urls)
            await svc.start(env, self.console, self.log_manager)

            # Start tunnel if requested
            if (svc.config.tunnel or self.share) and svc.config.port:
                self.console.print(f"[green][tunnel][/green] Opening Cloudflare Quick Tunnel for {name} (:{svc.config.port})...")
                tunnel = QuickTunnel(port=svc.config.port, service_name=name)
                self.tunnels[name] = tunnel
                try:
                    url = await tunnel.start(timeout=15.0)
                    self.tunnel_urls[name] = url
                    self.console.print(f"[bold green]✓ Live Tunnel Ready:[/] {url} -> localhost:{svc.config.port}")
                except Exception as e:
                    self.console.print(f"[bold red]Tunnel creation failed: {e}[/bold red]")

        # Boot dependent services with injected tunnel URLs
        for name, svc in other_svcs:
            env = resolve_environment_variables(svc.config, self.tunnel_urls)
            await svc.start(env, self.console, self.log_manager)

        self.console.rule("[bold green]All DevSnap Services Booted[/bold green]")
        self.console.print("[dim]Press Ctrl+C to stop all services.[/dim]\n")

        # Setup POSIX signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.initiate_shutdown)
            except NotImplementedError:
                # Windows or unsupported loop
                pass

        await self._stop_event.wait()

    def initiate_shutdown(self) -> None:
        self.console.print("\n[bold yellow]DevSnap Supervisor shutting down services...[/bold yellow]")
        for tunnel in self.tunnels.values():
            tunnel.stop()
        for svc in self.services.values():
            svc.stop()
        self._stop_event.set()

    def get_topology(self) -> Dict:
        """Returns topology status for MCP tools and status inspection."""
        return {
            "root": str(self.root),
            "tunnel_urls": self.tunnel_urls,
            "services": {
                name: {
                    "running": svc.is_running,
                    "cmd": svc.config.cmd,
                    "port": svc.config.port,
                    "cwd": svc.config.cwd,
                    "pid": svc.process.pid if svc.process else None,
                }
                for name, svc in self.services.items()
            },
            "sqlite_databases": self.config.state.sqlite,
            "env_files": self.config.env_files,
        }
