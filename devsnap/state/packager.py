from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict
from devsnap.config import DevSnapConfig
from devsnap.state.firebase_state import export_firebase_state
from devsnap.state.postgres_state import export_postgres_state, restore_postgres_state
from devsnap.state.sqlite_state import backup_sqlite, restore_sqlite


def pack_state_bundle(root: Path, config: DevSnapConfig, target_archive: Path) -> Path:
    """Collects secrets and database states into a tarball archive."""
    target_archive.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        staging = Path(tmp_dir) / "bundle"
        staging.mkdir(parents=True, exist_ok=True)
        secrets_dir = staging / "secrets"
        state_dir = staging / "state"
        secrets_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)

        manifest: Dict[str, Any] = {
            "version": config.version,
            "timestamp": time.time(),
            "env_files": [],
            "credential_files": {},
            "sqlite": [],
            "firebase": bool(config.state.firebase_emulators),
            "postgres": bool(config.state.postgres),
        }

        # 1. Collect .env files
        for env_rel in config.env_files:
            src = root / env_rel
            if src.is_file():
                dest = secrets_dir / env_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                manifest["env_files"].append(env_rel)

        # 2. Collect credential files
        for cred_key, cred_rel in config.credential_files.items():
            src = root / cred_rel
            if src.is_file():
                dest = secrets_dir / cred_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                manifest["credential_files"][cred_key] = cred_rel

        # 3. Snapshot SQLite databases
        for db_rel in config.state.sqlite:
            src = root / db_rel
            if src.is_file():
                dest = state_dir / "sqlite" / db_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                backup_sqlite(src, dest)
                manifest["sqlite"].append(db_rel)

        # 4. Snapshot Firebase Emulators if configured
        if config.state.firebase_emulators:
            fb_dest = state_dir / "firebase"
            export_firebase_state(fb_dest, cwd=root)

        # 5. Snapshot Postgres if configured
        if config.state.postgres:
            pg_dest = state_dir / "postgres" / "dump.pg"
            pg_cfg = config.state.postgres
            export_postgres_state(
                output_path=pg_dest,
                container=pg_cfg.container,
                db_name=pg_cfg.db_name,
                user=pg_cfg.user or "postgres",
                port=pg_cfg.port,
            )

        # Write manifest
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Create tarball
        with tarfile.open(target_archive, "w:gz") as tar:
            for item in staging.iterdir():
                tar.add(item, arcname=item.name)

    return target_archive


def unpack_state_bundle(archive_path: Path, root: Path, config: Optional[DevSnapConfig] = None) -> Dict[str, Any]:
    """Unpacks state tarball and restores secrets and database snapshots."""
    if not archive_path.is_file():
        raise FileNotFoundError(f"State archive not found: {archive_path}")

    with tempfile.TemporaryDirectory() as tmp_dir:
        staging = Path(tmp_dir) / "extracted"
        staging.mkdir(parents=True, exist_ok=True)

        with tarfile.open(archive_path, "r:gz") as tar:
            if hasattr(tarfile, "data_filter"):
                tar.extractall(path=staging, filter="data")
            else:
                tar.extractall(path=staging)

        manifest_file = staging / "manifest.json"
        manifest: Dict[str, Any] = {}
        if manifest_file.is_file():
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

        secrets_dir = staging / "secrets"
        state_dir = staging / "state"

        # 1. Restore .env files
        env_files = manifest.get("env_files", config.env_files if config else [])
        for env_rel in env_files:
            src = secrets_dir / env_rel
            if src.is_file():
                dest = root / env_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

        # 2. Restore credential files
        cred_files = manifest.get("credential_files", config.credential_files if config else {})
        for _, cred_rel in cred_files.items():
            src = secrets_dir / cred_rel
            if src.is_file():
                dest = root / cred_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

        # 3. Restore SQLite databases
        sqlite_dbs = manifest.get("sqlite", config.state.sqlite if config else [])
        for db_rel in sqlite_dbs:
            src = state_dir / "sqlite" / db_rel
            if src.is_file():
                dest = root / db_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                restore_sqlite(src, dest)

        # 4. Restore Firebase Emulator exports
        src_fb = state_dir / "firebase"
        if src_fb.is_dir():
            dest_fb = root / ".devsnap" / "state" / "firebase"
            dest_fb.parent.mkdir(parents=True, exist_ok=True)
            if dest_fb.exists():
                shutil.rmtree(dest_fb)
            shutil.copytree(src_fb, dest_fb)

        # 5. Restore Postgres if configured and present
        src_pg = state_dir / "postgres" / "dump.pg"
        if src_pg.is_file() and config and config.state.postgres:
            pg_cfg = config.state.postgres
            restore_postgres_state(
                dump_path=src_pg,
                container=pg_cfg.container,
                db_name=pg_cfg.db_name,
                user=pg_cfg.user or "postgres",
                port=pg_cfg.port,
            )

        return manifest
