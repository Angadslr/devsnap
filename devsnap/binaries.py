from __future__ import annotations

import os
import platform
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path
from typing import Optional
import httpx

AGE_VERSION = "v1.2.1"
CLOUDFLARED_BASE_URL = "https://github.com/cloudflare/cloudflared/releases/latest/download"


def get_global_bin_dir() -> Path:
    p = Path.home() / ".devsnap" / "bin"
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_binary(binary_name: str, env_override_var: Optional[str] = None) -> Optional[Path]:
    """Search for binary in ENV override, PATH, and ~/.devsnap/bin."""
    if env_override_var:
        env_val = os.getenv(env_override_var)
        if env_val and Path(env_val).is_file() and os.access(env_val, os.X_OK):
            return Path(env_val)

    # Check ~/.devsnap/bin
    global_bin = get_global_bin_dir() / binary_name
    if global_bin.is_file() and os.access(global_bin, os.X_OK):
        return global_bin

    # Check system PATH
    sys_path = shutil.which(binary_name)
    if sys_path:
        return Path(sys_path)

    return None


def get_age_path() -> Optional[Path]:
    return find_binary("age", "DEVSNAP_AGE_PATH")


def get_cloudflared_path() -> Optional[Path]:
    return find_binary("cloudflared", "DEVSNAP_CLOUDFLARED_PATH")


def download_age(dest_dir: Optional[Path] = None) -> Path:
    """Download static age binary for current OS/Arch into dest_dir."""
    target_dir = dest_dir or get_global_bin_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_bin = target_dir / "age"
    if target_bin.is_file() and os.access(target_bin, os.X_OK):
        return target_bin

    sys_os = platform.system().lower()
    machine = platform.machine().lower()

    if sys_os not in ["darwin", "linux"]:
        raise RuntimeError(f"Unsupported OS for automatic age download: {sys_os}")

    arch = "arm64" if ("arm" in machine or "aarch64" in machine) else "amd64"
    tarball_name = f"age-{AGE_VERSION}-{sys_os}-{arch}.tar.gz"
    url = f"https://github.com/FiloSottile/age/releases/download/{AGE_VERSION}/{tarball_name}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_tar = Path(tmpdir) / tarball_name
        with httpx.stream("GET", url, follow_redirects=True, timeout=30.0) as r:
            r.raise_for_status()
            with open(tmp_tar, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)

        with tarfile.open(tmp_tar, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("/age") or member.name == "age":
                    f = tar.extractfile(member)
                    if f:
                        with open(target_bin, "wb") as out_f:
                            out_f.write(f.read())
                        break

    target_bin.chmod(target_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target_bin


def download_cloudflared(dest_dir: Optional[Path] = None) -> Path:
    """Download cloudflared binary for current OS/Arch into dest_dir."""
    target_dir = dest_dir or get_global_bin_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_bin = target_dir / "cloudflared"
    if target_bin.is_file() and os.access(target_bin, os.X_OK):
        return target_bin

    sys_os = platform.system().lower()
    machine = platform.machine().lower()

    if sys_os == "darwin":
        binary_name = "cloudflared-darwin-arm64" if ("arm" in machine or "aarch64" in machine) else "cloudflared-darwin-amd64"
    elif sys_os == "linux":
        binary_name = "cloudflared-linux-arm64" if ("arm" in machine or "aarch64" in machine) else "cloudflared-linux-amd64"
    else:
        raise RuntimeError(f"Unsupported OS for cloudflared download: {sys_os}")

    url = f"{CLOUDFLARED_BASE_URL}/{binary_name}"
    with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
        r.raise_for_status()
        with open(target_bin, "wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)

    target_bin.chmod(target_bin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target_bin


def ensure_age() -> Path:
    p = get_age_path()
    if p:
        return p
    return download_age()


def ensure_cloudflared() -> Path:
    p = get_cloudflared_path()
    if p:
        return p
    return download_cloudflared()
