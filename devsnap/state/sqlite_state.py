from __future__ import annotations

import sqlite3
from pathlib import Path


def backup_sqlite(source_path: Path, dest_path: Path) -> None:
    """Hot-safe SQLite backup using sqlite3.Connection.backup()."""
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source database not found: {source_path}")

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    # Use URI mode=ro to avoid write lock contention on the active source
    src_uri = f"file:{source_path.resolve()}?mode=ro"
    src_conn = sqlite3.connect(src_uri, uri=True)
    dest_conn = sqlite3.connect(str(dest_path.resolve()))

    try:
        with dest_conn:
            src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()


def restore_sqlite(snapshot_path: Path, target_path: Path) -> None:
    """Safely restore a SQLite snapshot to target_path using Connection.backup()."""
    if not snapshot_path.is_file():
        raise FileNotFoundError(f"SQLite snapshot file not found: {snapshot_path}")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    snap_uri = f"file:{snapshot_path.resolve()}?mode=ro"
    snap_conn = sqlite3.connect(snap_uri, uri=True)
    target_conn = sqlite3.connect(str(target_path.resolve()))

    try:
        with target_conn:
            snap_conn.backup(target_conn)
    finally:
        target_conn.close()
        snap_conn.close()
