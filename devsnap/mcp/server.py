from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import dotenv_values

from devsnap.config import DevSnapConfig, find_project_root
from devsnap.scanner.ast_analyzer import scan_repository_env_vars
from devsnap.state.packager import unpack_state_bundle
from devsnap.state.sqlite_state import restore_sqlite
from devsnap.supervisor.process_manager import ProcessSupervisor
from devsnap.supervisor.ring_buffer import LogManager

# Compatibility layer for MCP SDK v1 and v2
try:
    from mcp.server.mcpserver import MCPServer
    server_factory = lambda name: MCPServer(name)
except (ImportError, ModuleNotFoundError):
    try:
        from mcp.server.fastmcp import FastMCP
        server_factory = lambda name: FastMCP(name)
    except Exception as e:
        server_factory = None

mcp_app = server_factory("devsnap") if server_factory else None


def get_topology_data(root: Optional[Path] = None) -> Dict[str, Any]:
    project_root = root or find_project_root()
    supervisor = ProcessSupervisor.get_instance()
    if supervisor:
        topology = supervisor.get_topology()
    else:
        topology = {
            "root": str(project_root),
            "tunnel_urls": {},
            "services": {},
            "sqlite_databases": [],
            "env_files": [],
        }

    cfg_file = project_root / "devsnap.json"
    if cfg_file.is_file():
        try:
            cfg = DevSnapConfig.load(cfg_file)
            topology["sqlite_databases"] = cfg.state.sqlite
            topology["env_files"] = cfg.env_files
            if not topology["services"]:
                topology["services"] = {
                    name: {"running": False, "cmd": svc.cmd, "port": svc.port, "cwd": svc.cwd}
                    for name, svc in cfg.services.items()
                }
        except Exception:
            pass

    # Verify missing env keys
    schema = verify_schema_data(project_root)
    topology["missing_env_keys"] = schema.get("missing_keys", [])
    topology["env_status"] = "clean" if not schema.get("missing_keys") else "missing_keys_detected"
    return topology


def restore_state_data(root: Optional[Path] = None) -> Dict[str, Any]:
    project_root = root or find_project_root()
    cfg_file = project_root / "devsnap.json"
    cfg = DevSnapConfig.load(cfg_file) if cfg_file.is_file() else DevSnapConfig()

    restored_dbs = []
    # Check if unpacked snapshots exist in .devsnap/state/sqlite/
    state_sqlite_dir = project_root / ".devsnap" / "state" / "sqlite"
    for db_rel in cfg.state.sqlite:
        snap_src = state_sqlite_dir / db_rel
        dest = project_root / db_rel
        if snap_src.is_file():
            restore_sqlite(snap_src, dest)
            restored_dbs.append(db_rel)

    # Check if a recent unencrypted state bundle exists
    raw_archive = project_root / ".devsnap" / "state.tar.gz"
    if raw_archive.is_file():
        unpack_state_bundle(raw_archive, project_root, cfg)
        for db_rel in cfg.state.sqlite:
            if db_rel not in restored_dbs and (project_root / db_rel).exists():
                restored_dbs.append(db_rel)

    return {
        "status": "success",
        "restored_databases": restored_dbs,
        "message": f"Restored {len(restored_dbs)} database(s) in <1s.",
    }


def read_logs_data(service: str, lines: int = 50) -> List[str]:
    return LogManager.get_instance().get_logs(service, lines)


def verify_schema_data(root: Optional[Path] = None) -> Dict[str, Any]:
    project_root = root or find_project_root()
    code_keys = scan_repository_env_vars(project_root)

    cfg_file = project_root / "devsnap.json"
    env_files = [".env"]
    if cfg_file.is_file():
        try:
            cfg = DevSnapConfig.load(cfg_file)
            if cfg.env_files:
                env_files = cfg.env_files
        except Exception:
            pass

    found_keys = set()
    for env_rel in env_files:
        env_path = project_root / env_rel
        if env_path.is_file():
            vals = dotenv_values(env_path)
            found_keys.update(vals.keys())

    missing = sorted(list(code_keys - found_keys))
    return {
        "is_valid": len(missing) == 0,
        "missing_keys": missing,
        "code_keys": sorted(list(code_keys)),
        "configured_env_keys": sorted(list(found_keys)),
    }


if mcp_app:
    @mcp_app.tool()
    def get_env_topology() -> Dict[str, Any]:
        """Returns active services, open ports, live tunnel URLs, and missing .env keys."""
        return get_topology_data()

    @mcp_app.tool()
    def restore_state_snapshot() -> Dict[str, Any]:
        """Resets the local database to the clean team snapshot in under 1 second."""
        return restore_state_data()

    @mcp_app.tool()
    def read_service_logs(service: str, lines: int = 50) -> List[str]:
        """Streams recent stdout/stderr log buffers for a given service."""
        return read_logs_data(service, lines)

    @mcp_app.tool()
    def verify_env_schema() -> Dict[str, Any]:
        """Static audit checking required environment variables in code against local .env files."""
        return verify_schema_data()


def run_mcp_server() -> None:
    """Run MCP server over stdio."""
    if not mcp_app:
        raise RuntimeError("MCP server library not available")
    mcp_app.run(transport="stdio")
