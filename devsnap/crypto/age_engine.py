from __future__ import annotations

import base64
import hashlib
import os
import subprocess
from pathlib import Path
from typing import List, Optional
from devsnap.binaries import ensure_age, get_age_path


class AgeCryptoError(Exception):
    """Exception raised when age encryption or decryption fails."""
    pass


def _mock_encrypt(input_path: Path, output_path: Path, recipients: List[str]) -> None:
    """Mock encryption for testing environments when DEVSNAP_MOCK_AGE is set."""
    data = input_path.read_bytes()
    header = b"DEVSNAP_MOCK_AGE_V1\n"
    recipients_tag = (",".join(recipients) + "\n").encode("utf-8")
    payload = base64.b64encode(data)
    output_path.write_bytes(header + recipients_tag + payload)


def _mock_decrypt(input_path: Path, output_path: Path, identity_path: Optional[Path]) -> None:
    """Mock decryption for testing environments when DEVSNAP_MOCK_AGE is set."""
    content = input_path.read_bytes()
    if not content.startswith(b"DEVSNAP_MOCK_AGE_V1\n"):
        raise AgeCryptoError("Invalid mock age payload")
    parts = content.split(b"\n", 2)
    if len(parts) < 3:
        raise AgeCryptoError("Malformed mock age payload")
    raw_payload = parts[2]
    decrypted = base64.b64decode(raw_payload)
    output_path.write_bytes(decrypted)


def encrypt_file(
    input_path: Path,
    output_path: Path,
    recipients_file: Optional[Path] = None,
    recipients: Optional[List[str]] = None,
    age_bin: Optional[Path] = None,
) -> None:
    """Encrypt input_path to output_path using age and given recipients."""
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Check for mock test mode
    if os.getenv("DEVSNAP_MOCK_AGE") == "1":
        recs = recipients or []
        if recipients_file and recipients_file.is_file():
            recs.extend([line.strip() for line in recipients_file.read_text().splitlines() if line.strip()])
        _mock_encrypt(input_path, output_path, recs)
        return

    binary = age_bin or get_age_path() or ensure_age()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(binary), "-o", str(output_path)]

    if recipients_file and recipients_file.is_file():
        cmd.extend(["-R", str(recipients_file)])
    elif recipients:
        for r in recipients:
            cmd.extend(["-r", r])
    else:
        raise ValueError("Must provide either recipients_file or recipients list for encryption.")

    cmd.append(str(input_path))

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AgeCryptoError(f"Age encryption failed (code {proc.returncode}): {proc.stderr}")


def decrypt_file(
    input_path: Path,
    output_path: Path,
    identity_path: Optional[Path] = None,
    age_bin: Optional[Path] = None,
) -> None:
    """Decrypt input_path to output_path using age and identity private key."""
    if not input_path.is_file():
        raise FileNotFoundError(f"Encrypted input file not found: {input_path}")

    # Check for mock test mode
    if os.getenv("DEVSNAP_MOCK_AGE") == "1":
        _mock_decrypt(input_path, output_path, identity_path)
        return

    binary = age_bin or get_age_path() or ensure_age()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(binary), "-d"]
    if identity_path:
        cmd.extend(["-i", str(identity_path)])
    cmd.extend(["-o", str(output_path), str(input_path)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AgeCryptoError(f"Age decryption failed (code {proc.returncode}): {proc.stderr}")
