import sqlite3
from pathlib import Path
from devsnap.state.sqlite_state import backup_sqlite, restore_sqlite


def test_sqlite_hot_backup_and_restore(tmp_path: Path):
    db_file = tmp_path / "app.db"
    snap_file = tmp_path / "snapshot.db"

    # 1. Create table and insert initial data
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users (name) VALUES ('Alice')")
        conn.execute("INSERT INTO users (name) VALUES ('Bob')")
    conn.close()

    # 2. Perform hot backup
    backup_sqlite(db_file, snap_file)
    assert snap_file.is_file()

    # 3. Mutate original DB (insert dirty row, delete Alice)
    conn = sqlite3.connect(db_file)
    with conn:
        conn.execute("DELETE FROM users WHERE name = 'Alice'")
        conn.execute("INSERT INTO users (name) VALUES ('DirtyData')")
    conn.close()

    # Verify mutation happened
    conn = sqlite3.connect(db_file)
    names = [r[0] for r in conn.execute("SELECT name FROM users").fetchall()]
    conn.close()
    assert names == ["Bob", "DirtyData"]

    # 4. Restore from snapshot
    restore_sqlite(snap_file, db_file)

    # 5. Verify restored state
    conn = sqlite3.connect(db_file)
    restored_names = [r[0] for r in conn.execute("SELECT name FROM users ORDER BY id").fetchall()]
    conn.close()
    assert restored_names == ["Alice", "Bob"]
