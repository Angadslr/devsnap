from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

DEVSNAP_REF = "refs/devsnap/latest"
DEFAULT_BLOB_FILENAME = "state.tar.gz.age"


def _run_git(args: list[str], cwd: Optional[Path] = None, stdin_bytes: Optional[bytes] = None) -> Tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_AUTHOR_NAME"] = env.get("GIT_AUTHOR_NAME", "DevSnap")
    env["GIT_AUTHOR_EMAIL"] = env.get("GIT_AUTHOR_EMAIL", "devsnap@local")
    env["GIT_COMMITTER_NAME"] = env.get("GIT_COMMITTER_NAME", "DevSnap")
    env["GIT_COMMITTER_EMAIL"] = env.get("GIT_COMMITTER_EMAIL", "devsnap@local")

    proc = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        input=stdin_bytes,
        capture_output=True,
        env=env,
    )
    stdout_str = proc.stdout.decode("utf-8", errors="replace").strip()
    stderr_str = proc.stderr.decode("utf-8", errors="replace").strip()
    return proc.returncode, stdout_str, stderr_str


def write_git_blob(file_path: Path, cwd: Optional[Path] = None) -> str:
    """Store raw file in Git object database as a blob and return its SHA."""
    if not file_path.is_file():
        raise FileNotFoundError(f"File to hash does not exist: {file_path}")
    rc, stdout, stderr = _run_git(["hash-object", "-w", str(file_path.resolve())], cwd=cwd)
    if rc != 0:
        raise RuntimeError(f"git hash-object failed: {stderr}")
    return stdout


def create_git_tree(blob_sha: str, filename: str = DEFAULT_BLOB_FILENAME, cwd: Optional[Path] = None) -> str:
    """Create a Git tree containing the state archive blob."""
    tree_input = f"100644 blob {blob_sha}\t{filename}\n".encode("utf-8")
    rc, stdout, stderr = _run_git(["mktree"], cwd=cwd, stdin_bytes=tree_input)
    if rc != 0:
        raise RuntimeError(f"git mktree failed: {stderr}")
    return stdout


def create_git_commit(tree_sha: str, message: str, cwd: Optional[Path] = None) -> str:
    """Create an orphan commit from a tree SHA."""
    rc, stdout, stderr = _run_git(["commit-tree", tree_sha, "-m", message], cwd=cwd)
    if rc != 0:
        raise RuntimeError(f"git commit-tree failed: {stderr}")
    return stdout


def update_git_ref(ref_name: str, commit_sha: str, cwd: Optional[Path] = None) -> None:
    """Atomically update a Git ref to point to the commit SHA."""
    rc, stdout, stderr = _run_git(["update-ref", ref_name, commit_sha], cwd=cwd)
    if rc != 0:
        raise RuntimeError(f"git update-ref failed: {stderr}")


def push_git_ref(ref_name: str = DEVSNAP_REF, remote: str = "origin", cwd: Optional[Path] = None) -> Tuple[bool, str]:
    """Push the Git ref to remote origin."""
    rc, stdout, stderr = _run_git(["push", remote, f"{ref_name}:{ref_name}"], cwd=cwd)
    if rc == 0:
        return True, stdout
    return False, stderr


def fetch_git_ref(ref_name: str = DEVSNAP_REF, remote: str = "origin", cwd: Optional[Path] = None) -> Tuple[bool, str]:
    """Fetch the Git ref from remote origin into local ref."""
    rc, stdout, stderr = _run_git(["fetch", remote, f"{ref_name}:{ref_name}"], cwd=cwd)
    if rc == 0:
        return True, stdout
    return False, stderr


def extract_git_blob(
    output_path: Path,
    ref_name: str = DEVSNAP_REF,
    filename: str = DEFAULT_BLOB_FILENAME,
    cwd: Optional[Path] = None,
) -> bool:
    """Extract blob content directly from ref:filename using git cat-file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"

    proc = subprocess.run(
        ["git", "cat-file", "-p", f"{ref_name}:{filename}"],
        cwd=cwd,
        capture_output=True,
        env=env,
    )
    if proc.returncode != 0:
        return False

    output_path.write_bytes(proc.stdout)
    return True


def save_state_to_git(
    archive_path: Path,
    message: str = "devsnap save state",
    ref_name: str = DEVSNAP_REF,
    cwd: Optional[Path] = None,
) -> str:
    """Store state archive into Git plumbing ref and return commit SHA."""
    blob_sha = write_git_blob(archive_path, cwd=cwd)
    tree_sha = create_git_tree(blob_sha, filename=DEFAULT_BLOB_FILENAME, cwd=cwd)
    commit_sha = create_git_commit(tree_sha, message=message, cwd=cwd)
    update_git_ref(ref_name, commit_sha, cwd=cwd)
    return commit_sha
