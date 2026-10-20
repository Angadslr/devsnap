from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from devsnap.config import (
    CONFIG_FILE_NAME,
    DevSnapConfig,
    find_project_root,
    get_dot_devsnap_path,
)
from devsnap.crypto.age_engine import decrypt_file, encrypt_file
from devsnap.crypto.ssh_keys import resolve_identity_path
from devsnap.mcp.server import get_topology_data, restore_state_data, run_mcp_server, verify_schema_data
from devsnap.scanner.ast_analyzer import scan_repository_env_vars
from devsnap.scanner.detectors import build_scanned_config
from devsnap.scanner.git_info import (
    fetch_github_ssh_keys,
    get_git_remote_url,
    parse_github_owner_repo,
    read_recipients_file,
    save_recipients_file,
)
from devsnap.state.packager import pack_state_bundle, unpack_state_bundle
from devsnap.supervisor.process_manager import ProcessSupervisor
from devsnap.transport.git_plumbing import (
    DEVSNAP_REF,
    extract_git_blob,
    fetch_git_ref,
    push_git_ref,
    save_state_to_git,
)

app = typer.Typer(
    name="devsnap",
    help="DevSnap: Branch application state, secrets, and local tunnels in one command.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def init(
    collaborator: Optional[list[str]] = typer.Option(
        None, "--collaborator", "-c", help="GitHub username(s) to grant state access to."
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Overwrite existing devsnap.json."),
) -> None:
    """Scan the repository AST and framework config to auto-generate devsnap.json and recipient keys."""
    root = find_project_root()
    cfg_file = root / CONFIG_FILE_NAME

    if cfg_file.is_file() and not force:
        console.print(f"[yellow]Warning:[/] {CONFIG_FILE_NAME} already exists. Use --force to regenerate.")
        return

    with console.status("[bold cyan]Scanning repository AST, frameworks, and environment variables...[/bold cyan]"):
        scanned_config = build_scanned_config(root)

        # Detect Git remote and collaborator
        remote_url = get_git_remote_url(root)
        collaborators = list(collaborator) if collaborator else []
        if remote_url:
            parsed = parse_github_owner_repo(remote_url)
            if parsed and parsed[0] not in collaborators:
                collaborators.append(parsed[0])

        scanned_config.collaborators = collaborators

        # Fetch collaborator SSH keys
        all_keys = []
        for user in collaborators:
            keys = fetch_github_ssh_keys(user)
            all_keys.extend(keys)

        dot_devsnap = get_dot_devsnap_path(root)
        dot_devsnap.mkdir(parents=True, exist_ok=True)
        recipients_file = dot_devsnap / "recipients.txt"
        if all_keys:
            save_recipients_file(all_keys, recipients_file)

        # Save config
        scanned_config.save(cfg_file)

    # Ensure .gitignore ignores .devsnap
    gitignore = root / ".gitignore"
    if gitignore.is_file():
        gi_text = gitignore.read_text(encoding="utf-8")
        if ".devsnap" not in gi_text:
            gitignore.write_text(gi_text.rstrip() + "\n.devsnap/\n", encoding="utf-8")
    else:
        gitignore.write_text(".devsnap/\n", encoding="utf-8")

    console.print(Panel(
        f"[bold green]✓ DevSnap initialized successfully![/bold green]\n\n"
        f"• Project Root: [cyan]{root}[/cyan]\n"
        f"• Config File: [cyan]{cfg_file}[/cyan]\n"
        f"• Detected Env Files: [cyan]{scanned_config.env_files}[/cyan]\n"
        f"• Detected SQLite DBs: [cyan]{scanned_config.state.sqlite}[/cyan]\n"
        f"• Discovered Services: [cyan]{list(scanned_config.services.keys())}[/cyan]\n"
        f"• Collaborator Keys: [cyan]{len(all_keys)} keys saved to .devsnap/recipients.txt[/cyan]",
        title="DevSnap Init",
        border_style="green",
    ))


@app.command()
def push(
    message: str = typer.Option("DevSnap save state", "--message", "-m", help="Snapshot commit message."),
    no_push: bool = typer.Option(False, "--no-push", help="Only save snapshot to local Git ref without pushing to remote."),
) -> None:
    """Capture local secrets and database state, encrypt them, and store to Git plumbing ref."""
    root = find_project_root()
    cfg_file = root / CONFIG_FILE_NAME
    if not cfg_file.is_file():
        console.print(f"[red]Error:[/] {CONFIG_FILE_NAME} not found. Run [bold]devsnap init[/bold] first.")
        raise typer.Exit(1)

    cfg = DevSnapConfig.load(cfg_file)
    dot_devsnap = get_dot_devsnap_path(root)
    dot_devsnap.mkdir(parents=True, exist_ok=True)
    raw_tarball = dot_devsnap / "state.tar.gz"
    enc_tarball = dot_devsnap / "state.tar.gz.age"
    recipients_file = dot_devsnap / "recipients.txt"

    with console.status("[bold cyan]Capturing local state and database hot-backup...[/bold cyan]"):
        pack_state_bundle(root, cfg, raw_tarball)

    # Check recipient keys
    if not recipients_file.is_file() or not read_recipients_file(recipients_file):
        # Refresh from collaborators in config or git remote
        all_keys = []
        for user in cfg.collaborators:
            all_keys.extend(fetch_github_ssh_keys(user))
        if all_keys:
            save_recipients_file(all_keys, recipients_file)
        else:
            # Fallback to local user identity public key or mock
            id_path = resolve_identity_path()
            if id_path and Path(str(id_path) + ".pub").is_file():
                pub_key = Path(str(id_path) + ".pub").read_text(encoding="utf-8").strip()
                save_recipients_file([pub_key], recipients_file)
            else:
                console.print(
                    "[yellow]Warning:[/] No collaborator SSH keys in .devsnap/recipients.txt. "
                    "Run 'devsnap keys add <github-username>' to add teammates."
                )
                if not os.getenv("DEVSNAP_MOCK_AGE"):
                    console.print("[red]Error: Cannot encrypt without at least one recipient key.[/red]")
                    raise typer.Exit(1)

    with console.status("[bold cyan]Encrypting state archive with age...[/bold cyan]"):
        try:
            encrypt_file(raw_tarball, enc_tarball, recipients_file=recipients_file)
        except Exception as e:
            console.print(f"[red]Encryption failed:[/] {e}")
            raise typer.Exit(1)

    with console.status("[bold cyan]Saving encrypted snapshot to Git plumbing ref...[/bold cyan]"):
        commit_sha = save_state_to_git(enc_tarball, message=message, cwd=root)

    pushed = False
    remote_msg = ""
    if not no_push and get_git_remote_url(root):
        with console.status("[bold cyan]Pushing snapshot ref to origin...[/bold cyan]"):
            ok, remote_msg = push_git_ref(ref_name=DEVSNAP_REF, remote="origin", cwd=root)
            pushed = ok

    console.print(Panel(
        f"[bold green]✓ DevSnap state snapshot saved successfully![/bold green]\n\n"
        f"• Commit SHA: [cyan]{commit_sha}[/cyan]\n"
        f"• Git Ref: [cyan]{DEVSNAP_REF}[/cyan]\n"
        f"• Remote Push: [cyan]{'Pushed to origin' if pushed else ('Skipped or remote not reachable: ' + remote_msg if remote_msg else 'Local ref only')}[/cyan]\n"
        f"• Databases Snapshotted: [cyan]{cfg.state.sqlite}[/cyan]\n"
        f"• Secrets Encrypted: [cyan]{cfg.env_files}[/cyan]",
        title="DevSnap Push",
        border_style="green",
    ))


@app.command()
def pull(
    identity: Optional[str] = typer.Option(
        None, "--identity", "-i", help="Path to SSH private key for age decryption (~/.ssh/id_ed25519)."
    ),
    local_only: bool = typer.Option(False, "--local-only", help="Do not fetch from remote origin before restoring."),
) -> None:
    """Fetch encrypted state from Git ref, decrypt with local SSH key, and hydrate secrets + DBs."""
    root = find_project_root()
    cfg_file = root / CONFIG_FILE_NAME
    cfg = DevSnapConfig.load(cfg_file) if cfg_file.is_file() else DevSnapConfig()

    dot_devsnap = get_dot_devsnap_path(root)
    dot_devsnap.mkdir(parents=True, exist_ok=True)
    enc_tarball = dot_devsnap / "state.tar.gz.age"
    raw_tarball = dot_devsnap / "state.tar.gz"

    if not local_only and get_git_remote_url(root):
        with console.status("[bold cyan]Fetching state ref from origin...[/bold cyan]"):
            fetch_git_ref(ref_name=DEVSNAP_REF, remote="origin", cwd=root)

    with console.status("[bold cyan]Extracting encrypted state from Git object database...[/bold cyan]"):
        extracted = extract_git_blob(enc_tarball, ref_name=DEVSNAP_REF, cwd=root)
        if not extracted and not enc_tarball.is_file():
            console.print(f"[red]Error:[/] No state snapshot found in {DEVSNAP_REF} or local cache.")
            raise typer.Exit(1)

    # Resolve decryption identity
    id_path = resolve_identity_path(identity)
    if not id_path and not os.getenv("DEVSNAP_MOCK_AGE"):
        console.print(
            "[red]Error:[/] No SSH private key found in ~/.ssh (e.g. id_ed25519 or id_rsa). "
            "Please specify one via --identity /path/to/key."
        )
        raise typer.Exit(1)

    with console.status(f"[bold cyan]Decrypting state bundle with {id_path or 'mock identity'}...[/bold cyan]"):
        try:
            decrypt_file(enc_tarball, raw_tarball, identity_path=id_path)
        except Exception as e:
            console.print(f"[red]Decryption failed:[/] {e}")
            console.print("[dim]Ensure your public key was added to .devsnap/recipients.txt by the sender.[/dim]")
            raise typer.Exit(1)

    with console.status("[bold cyan]Hydrating .env secrets and database snapshots...[/bold cyan]"):
        manifest = unpack_state_bundle(raw_tarball, root, cfg)

    console.print(Panel(
        f"[bold green]✓ DevSnap state hydrated successfully in <3 seconds![/bold green]\n\n"
        f"• Restored Env Files: [cyan]{manifest.get('env_files', [])}[/cyan]\n"
        f"• Restored Databases: [cyan]{manifest.get('sqlite', [])}[/cyan]\n"
        f"• Decryption Key: [cyan]{id_path or 'mock'}[/cyan]",
        title="DevSnap Pull",
        border_style="green",
    ))


@app.command()
def up(
    share: bool = typer.Option(False, "--share", "-s", help="Open Cloudflare Quick Tunnels for backend services."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate topology without launching child processes."),
) -> None:
    """Multiplexed boot: starts databases/emulators, backend, tunnels, and dependent mobile/frontends."""
    root = find_project_root()
    cfg_file = root / CONFIG_FILE_NAME
    if not cfg_file.is_file():
        console.print(f"[red]Error:[/] {CONFIG_FILE_NAME} not found. Run [bold]devsnap init[/bold] first.")
        raise typer.Exit(1)

    cfg = DevSnapConfig.load(cfg_file)
    if dry_run:
        console.print(Panel(
            f"[bold green]✓ DevSnap configuration is valid for boot.[/bold green]\n\n"
            f"• Services: [cyan]{list(cfg.services.keys())}[/cyan]\n"
            f"• Share mode: [cyan]{share}[/cyan]\n"
            f"• State: [cyan]{cfg.state.sqlite}[/cyan]",
            title="DevSnap Up (Dry Run)",
            border_style="green",
        ))
        return

    supervisor = ProcessSupervisor(config=cfg, root=root, share=share)
    try:
        asyncio.run(supervisor.start())
    except KeyboardInterrupt:
        pass


@app.command()
def mcp() -> None:
    """Start the FastMCP stdio server for AI coding agents (Cursor / Claude Code)."""
    try:
        run_mcp_server()
    except Exception as e:
        console.print(f"[red]MCP Server Error:[/] {e}", file=sys.stderr)
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """Inspect environment topology, live services, tunnel URLs, and .env schema health."""
    root = find_project_root()
    topology = get_topology_data(root)
    schema = verify_schema_data(root)

    table = Table(title="DevSnap Topology & Health")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Project Root", topology["root"])
    table.add_row("Active Tunnels", str(topology.get("tunnel_urls") or "None"))
    table.add_row("SQLite Databases", str(topology.get("sqlite_databases") or "None"))
    table.add_row("Configured Env Files", str(topology.get("env_files") or "None"))

    services_str = ", ".join(f"{k} (running: {v.get('running')})" for k, v in topology.get("services", {}).items())
    table.add_row("Services", services_str or "None")

    schema_status = "[bold green]Clean[/bold green]" if schema["is_valid"] else f"[bold red]Missing: {schema['missing_keys']}[/bold red]"
    table.add_row("Env Schema Audit", schema_status)

    console.print(table)


@app.command(name="restore")
def restore_cmd() -> None:
    """Quick hot-reset of local SQLite databases from the latest team snapshot."""
    root = find_project_root()
    res = restore_state_data(root)
    if res.get("status") == "success":
        console.print(f"[bold green]✓[/bold green] {res.get('message')}")
    else:
        console.print(f"[red]Restore failed:[/] {res}")


@app.command(name="keys")
def keys_cmd(
    action: str = typer.Argument("list", help="list or add"),
    username: Optional[str] = typer.Argument(None, help="GitHub username to add"),
) -> None:
    """Manage collaborator public SSH recipient keys."""
    root = find_project_root()
    dot_devsnap = get_dot_devsnap_path(root)
    recipients_file = dot_devsnap / "recipients.txt"

    if action == "list":
        keys = read_recipients_file(recipients_file)
        console.print(f"[bold cyan]Recipients in {recipients_file}:[/bold cyan] ({len(keys)} key(s))")
        for idx, k in enumerate(keys, 1):
            parts = k.split()
            key_type = parts[0] if parts else "unknown"
            key_comment = parts[2] if len(parts) > 2 else ""
            console.print(f" {idx}. [green]{key_type}[/green] [dim]{k[:30]}...[/dim] {key_comment}")
    elif action == "add":
        if not username:
            console.print("[red]Error:[/] Please provide a GitHub username.")
            raise typer.Exit(1)
        with console.status(f"Fetching keys for GitHub user [bold]{username}[/bold]..."):
            keys = fetch_github_ssh_keys(username)
        if not keys:
            console.print(f"[yellow]No public SSH keys found on GitHub for user '{username}'.[/yellow]")
            return
        existing = read_recipients_file(recipients_file)
        save_recipients_file(existing + keys, recipients_file)
        console.print(f"[bold green]✓ Added {len(keys)} key(s) for user '{username}' to {recipients_file}.[/bold green]")
    else:
        console.print(f"[red]Unknown action: {action}. Use 'list' or 'add <username>'.[/red]")


if __name__ == "__main__":
    app()
