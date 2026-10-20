import sqlite3
from pathlib import Path
from devsnap.config import DevSnapConfig, ServiceConfig, StateConfig
from devsnap.mcp.server import get_topology_data, read_logs_data, restore_state_data, verify_schema_data
from devsnap.state.sqlite_state import backup_sqlite
from devsnap.supervisor.ring_buffer import LogManager


def test_mcp_verify_schema(tmp_path: Path):
    # Code references JWT_SECRET and DATABASE_URL
    (tmp_path / "main.py").write_text(
        "import os\nx = os.getenv('JWT_SECRET')\ny = os.environ['DATABASE_URL']",
        encoding="utf-8",
    )

    # .env only defines JWT_SECRET
    (tmp_path / ".env").write_text("JWT_SECRET=supersecret\n", encoding="utf-8")

    cfg = DevSnapConfig(env_files=[".env"])
    cfg.save(tmp_path / "devsnap.json")

    schema = verify_schema_data(tmp_path)
    assert schema["is_valid"] is False
    assert schema["missing_keys"] == ["DATABASE_URL"]
    assert "JWT_SECRET" in schema["configured_env_keys"]


def test_mcp_read_logs():
    lm = LogManager.get_instance()
    lm.log("backend", "Startup line 1")
    lm.log("backend", "Ready on port 8000")

    logs = read_logs_data("backend", lines=10)
    assert len(logs) >= 2
    assert "Ready on port 8000" in logs[-1]


def test_mcp_restore_state(tmp_path: Path):
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("CREATE TABLE items (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO items VALUES (1, 'initial')")
    conn.close()

    # Save to .devsnap/state/sqlite/app.db
    snap_dir = tmp_path / ".devsnap" / "state" / "sqlite"
    snap_dir.mkdir(parents=True)
    backup_sqlite(db_file, snap_dir / "app.db")

    # Mutate DB
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("DELETE FROM items")
        conn.execute("INSERT INTO items VALUES (2, 'dirty')")
    conn.close()

    cfg = DevSnapConfig(state=StateConfig(sqlite=["app.db"]))
    cfg.save(tmp_path / "devsnap.json")

    result = restore_state_data(tmp_path)
    assert result["status"] == "success"
    assert "app.db" in result["restored_databases"]

    # Verify original records restored
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT id, val FROM items").fetchall()
    conn.close()
    assert rows == [(1, "initial")]
