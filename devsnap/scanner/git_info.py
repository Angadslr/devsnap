from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
import httpx

GITHUB_REMOTE_REGEX = re.compile(
    r"""(?:git@github\.com:|https?://github\.com/)(?P<owner>[^/]+)/(?P<repo>[^/\.]+)(?:\.git)?"""
)


def run_git_command(args: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    proc = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def get_git_remote_url(cwd: Optional[Path] = None) -> Optional[str]:
    rc, stdout, _ = run_git_command(["remote", "get-url", "origin"], cwd=cwd)
    if rc == 0 and stdout:
        return stdout
    return None


def parse_github_owner_repo(remote_url: str) -> Optional[Tuple[str, str]]:
    m = GITHUB_REMOTE_REGEX.search(remote_url)
    if m:
        return m.group("owner"), m.group("repo")
    return None


def fetch_github_ssh_keys(username: str, timeout: float = 10.0) -> List[str]:
    """Fetch public SSH keys from https://github.com/{username}.keys."""
    url = f"https://github.com/{username.strip()}.keys"
    valid_keys: List[str] = []
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    cleaned = line.strip()
                    if cleaned.startswith("ssh-ed25519") or cleaned.startswith("ssh-rsa"):
                        valid_keys.append(cleaned)
    except Exception:
        pass
    return valid_keys


def save_recipients_file(keys: List[str], target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    # Deduplicate while preserving order
    unique_keys = list(dict.fromkeys(k.strip() for k in keys if k.strip()))
    target_path.write_text("\n".join(unique_keys) + ("\n" if unique_keys else ""), encoding="utf-8")


def read_recipients_file(target_path: Path) -> List[str]:
    if not target_path.is_file():
        return []
    lines = target_path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]
