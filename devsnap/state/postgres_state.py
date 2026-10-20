from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def export_postgres_state(
    output_path: Path,
    container: Optional[str] = None,
    db_name: str = "app",
    user: str = "postgres",
    port: int = 5432,
) -> bool:
    """Exports Postgres database using pg_dump (custom archive format -Fc)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if container:
        cmd = [
            "docker",
            "exec",
            "-t",
            container,
            "pg_dump",
            "-U",
            user,
            "-d",
            db_name,
            "-Fc",
        ]
        try:
            with open(output_path, "wb") as f:
                proc = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE)
            return proc.returncode == 0
        except Exception:
            return False
    else:
        cmd = ["pg_dump", "-p", str(port), "-U", user, "-d", db_name, "-Fc", "-f", str(output_path)]
        try:
            proc = subprocess.run(cmd, capture_output=True)
            return proc.returncode == 0
        except Exception:
            return False


def restore_postgres_state(
    dump_path: Path,
    container: Optional[str] = None,
    db_name: str = "app",
    user: str = "postgres",
    port: int = 5432,
) -> bool:
    """Restores Postgres database using pg_restore."""
    if not dump_path.is_file():
        return False

    if container:
        # Stream dump into docker exec pg_restore
        cmd = [
            "docker",
            "exec",
            "-i",
            container,
            "pg_restore",
            "-U",
            user,
            "-d",
            db_name,
            "--clean",
            "--if-exists",
        ]
        try:
            with open(dump_path, "rb") as f:
                proc = subprocess.run(cmd, stdin=f, capture_output=True)
            return proc.returncode == 0
        except Exception:
            return False
    else:
        cmd = [
            "pg_restore",
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            db_name,
            "--clean",
            "--if-exists",
            str(dump_path),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True)
            return proc.returncode == 0
        except Exception:
            return False
