from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def export_firebase_state(export_dir: Path, cwd: Optional[Path] = None) -> bool:
    """Exports Firebase Emulator data using firebase-tools CLI."""
    export_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["firebase", "emulators:export", str(export_dir.resolve()), "--force"]
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return proc.returncode == 0
    except FileNotFoundError:
        # firebase command not in path
        return False


def get_firebase_import_flag(import_dir: Path) -> str:
    return f"--import={import_dir.resolve()}"
