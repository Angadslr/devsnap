from pathlib import Path
from devsnap.config import DevSnapConfig, ServiceConfig, StateConfig, find_project_root


def test_config_serialization(tmp_path: Path):
    cfg = DevSnapConfig(
        version="1.0",
        collaborators=["octocat", "alice"],
        env_files=[".env", "mobile/.env"],
        credential_files={"GOOGLE_APPLICATION_CREDENTIALS": "service-account.json"},
        state=StateConfig(sqlite=["backend/app.db"]),
        services={
            "backend": ServiceConfig(cmd="uvicorn main:app --port 8000", port=8000, tunnel=True),
            "mobile": ServiceConfig(cmd="npx expo start --tunnel", inject_env={"API": "$services.backend.tunnel_url"}),
        },
    )

    cfg_file = tmp_path / "devsnap.json"
    cfg.save(cfg_file)
    assert cfg_file.is_file()

    loaded = DevSnapConfig.load(cfg_file)
    assert loaded.version == "1.0"
    assert "octocat" in loaded.collaborators
    assert loaded.state.sqlite == ["backend/app.db"]
    assert loaded.services["backend"].tunnel is True
    assert loaded.services["mobile"].inject_env["API"] == "$services.backend.tunnel_url"


def test_find_project_root(tmp_path: Path):
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    (tmp_path / "devsnap.json").write_text("{}", encoding="utf-8")

    root = find_project_root(sub)
    assert root == tmp_path
