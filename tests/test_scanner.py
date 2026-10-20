from pathlib import Path
from devsnap.scanner.ast_analyzer import scan_js_ts_code, scan_python_code, scan_repository_env_vars
from devsnap.scanner.detectors import build_scanned_config, detect_env_files, detect_sqlite_databases
from devsnap.scanner.git_info import parse_github_owner_repo


def test_scan_python_code():
    code = """
import os

db_url = os.getenv("DATABASE_URL")
secret = os.environ.get("SECRET_KEY")
api_key = os.environ["STRIPE_API_KEY"]
fallback = os.getenv("ANOTHER_VAR", "default")
"""
    keys = scan_python_code(code)
    assert keys == {"DATABASE_URL", "SECRET_KEY", "STRIPE_API_KEY", "ANOTHER_VAR"}


def test_scan_js_ts_code():
    code = """
const api = process.env.EXPO_PUBLIC_API_URL;
const nodeEnv = process.env['NODE_ENV'];
console.log(process.env.FIREBASE_PROJECT_ID);
"""
    keys = scan_js_ts_code(code)
    assert keys == {"EXPO_PUBLIC_API_URL", "NODE_ENV", "FIREBASE_PROJECT_ID"}


def test_scan_repository(tmp_path: Path):
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "main.py").write_text("import os\nval = os.getenv('JWT_SECRET')", encoding="utf-8")

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "App.tsx").write_text("const u = process.env.VITE_SERVER_URL;", encoding="utf-8")

    # Ignored directory
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "ignored.py").write_text("import os\nx = os.getenv('IGNORED_VAR')", encoding="utf-8")

    all_keys = scan_repository_env_vars(tmp_path)
    assert "JWT_SECRET" in all_keys
    assert "VITE_SERVER_URL" in all_keys
    assert "IGNORED_VAR" not in all_keys


def test_framework_detectors(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("dependencies = ['fastapi', 'uvicorn']", encoding="utf-8")
    (tmp_path / ".env").write_text("PORT=8000", encoding="utf-8")
    (tmp_path / "app.db").write_text("", encoding="utf-8")

    mobile = tmp_path / "mobile"
    mobile.mkdir()
    (mobile / "package.json").write_text('{"dependencies": {"expo": "~50.0.0"}}', encoding="utf-8")

    config = build_scanned_config(tmp_path)
    assert ".env" in config.env_files
    assert "app.db" in config.state.sqlite
    assert "backend" in config.services
    assert config.services["backend"].port == 8000
    assert "mobile" in config.services
    assert config.services["mobile"].inject_env["EXPO_PUBLIC_API_URL"] == "$services.backend.tunnel_url"


def test_parse_github_owner_repo():
    url_ssh = "git@github.com:myteam/myrepo.git"
    url_https = "https://github.com/myteam/myrepo.git"
    url_https_plain = "https://github.com/myteam/myrepo"

    assert parse_github_owner_repo(url_ssh) == ("myteam", "myrepo")
    assert parse_github_owner_repo(url_https) == ("myteam", "myrepo")
    assert parse_github_owner_repo(url_https_plain) == ("myteam", "myrepo")
