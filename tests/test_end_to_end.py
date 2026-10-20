import sqlite3
from pathlib import Path
from typer.testing import CliRunner

from devsnap.cli import app
from devsnap.transport.git_plumbing import _run_git

runner = CliRunner()


def test_full_devsnap_lifecycle(tmp_path: Path, monkeypatch):
    # Set cwd to tmp_path
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEVSNAP_MOCK_AGE", "1")
    monkeypatch.setenv("DEVSNAP_MOCK_TUNNEL", "1")

    # 1. Initialize git repo
    _run_git(["init"], cwd=tmp_path)

    # 2. Setup demo project files
    backend_dir = tmp_path / "app"
    backend_dir.mkdir()
    (backend_dir / "main.py").write_text(
        "import os\napi_key = os.getenv('SUPER_SECRET_KEY')\ndb_url = os.environ.get('DATABASE_URL')",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text("dependencies = ['fastapi', 'uvicorn']", encoding="utf-8")
    (tmp_path / ".env").write_text("SUPER_SECRET_KEY=dev_secret_999\nDATABASE_URL=sqlite:///app.db\n", encoding="utf-8")

    # Create SQLite DB with initial rows
    db_path = tmp_path / "app.db"
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("CREATE TABLE team (id INTEGER PRIMARY KEY, member TEXT, role TEXT)")
        conn.execute("INSERT INTO team (member, role) VALUES ('Alice', 'Backend Lead')")
        conn.execute("INSERT INTO team (member, role) VALUES ('Bob', 'Mobile Engineer')")
    conn.close()

    # 3. Test devsnap init
    init_res = runner.invoke(app, ["init", "--collaborator", "octocat"])
    assert init_res.exit_code == 0
    assert (tmp_path / "devsnap.json").is_file()

    # Add mock recipient key so push can encrypt
    recipients_file = tmp_path / ".devsnap" / "recipients.txt"
    recipients_file.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITESTKEY octocat@github\n", encoding="utf-8")

    # 4. Test devsnap push
    push_res = runner.invoke(app, ["push", "-m", "Initial team snapshot", "--no-push"])
    assert push_res.exit_code == 0
    assert "DevSnap state snapshot saved successfully" in push_res.stdout

    # 5. Simulate corruption or second machine clone
    (tmp_path / ".env").unlink()
    assert not (tmp_path / ".env").exists()

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("DELETE FROM team")
    conn.close()

    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT count(*) FROM team").fetchone()[0]
    conn.close()
    assert count == 0

    # 6. Test devsnap pull
    pull_res = runner.invoke(app, ["pull", "--local-only"])
    assert pull_res.exit_code == 0
    assert "DevSnap state hydrated successfully" in pull_res.stdout

    # Verify .env restored
    assert (tmp_path / ".env").is_file()
    assert "dev_secret_999" in (tmp_path / ".env").read_text(encoding="utf-8")

    # Verify SQLite database rows hydrated
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT member, role FROM team ORDER BY id").fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0] == ("Alice", "Backend Lead")
    assert rows[1] == ("Bob", "Mobile Engineer")

    # 7. Test devsnap status
    status_res = runner.invoke(app, ["status"])
    assert status_res.exit_code == 0
    assert "DevSnap Topology & Health" in status_res.stdout

    # 8. Test devsnap up --dry-run
    up_res = runner.invoke(app, ["up", "--dry-run"])
    assert up_res.exit_code == 0
    assert "DevSnap configuration is valid for boot" in up_res.stdout
