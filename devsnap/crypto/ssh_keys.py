from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


DEFAULT_KEY_FILENAMES = [
    "id_ed25519",
    "id_rsa",
    "id_ecdsa",
]


def find_default_identities(ssh_dir: Optional[Path] = None) -> List[Path]:
    """Search for private key files suitable for age decryption."""
    base_ssh = ssh_dir or (Path.home() / ".ssh")
    found: List[Path] = []

    if base_ssh.is_dir():
        for fname in DEFAULT_KEY_FILENAMES:
            candidate = base_ssh / fname
            if candidate.is_file():
                found.append(candidate)

    # Check for age identity
    age_identity = Path.home() / ".age" / "key.txt"
    if age_identity.is_file():
        found.append(age_identity)

    return found


def resolve_identity_path(identity_arg: Optional[str] = None) -> Optional[Path]:
    """Resolve explicit identity path or auto-discover from default locations."""
    if identity_arg:
        p = Path(identity_arg).expanduser().resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Specified identity file does not exist: {identity_arg}")

    defaults = find_default_identities()
    if defaults:
        return defaults[0]
    return None
