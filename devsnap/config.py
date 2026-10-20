from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

CONFIG_FILE_NAME = "devsnap.json"
DOT_DEVSNAP_DIR = ".devsnap"


class FirebaseEmulatorsConfig(BaseModel):
    config: str = "firebase.json"
    ports: List[int] = Field(default_factory=lambda: [4000, 8080, 9099])


class PostgresConfig(BaseModel):
    container: Optional[str] = None
    db_name: str = "app"
    port: int = 5432
    user: Optional[str] = "postgres"


class StateConfig(BaseModel):
    sqlite: List[str] = Field(default_factory=list)
    firebase_emulators: Optional[FirebaseEmulatorsConfig] = None
    postgres: Optional[PostgresConfig] = None


class ServiceConfig(BaseModel):
    cmd: str
    cwd: Optional[str] = None
    port: Optional[int] = None
    tunnel: bool = False
    inject_env: Dict[str, str] = Field(default_factory=dict)


class DevSnapConfig(BaseModel):
    version: str = "1.0"
    collaborators: List[str] = Field(default_factory=list)
    env_files: List[str] = Field(default_factory=lambda: [".env"])
    credential_files: Dict[str, str] = Field(default_factory=dict)
    state: StateConfig = Field(default_factory=StateConfig)
    services: Dict[str, ServiceConfig] = Field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str = CONFIG_FILE_NAME) -> DevSnapConfig:
        cfg_path = Path(path)
        if not cfg_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {cfg_path.resolve()}")
        with open(cfg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.model_validate(data)

    def save(self, path: Path | str = CONFIG_FILE_NAME) -> None:
        cfg_path = Path(path)
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))


def find_project_root(start: Optional[Path] = None) -> Path:
    """Traverse upwards to find devsnap.json or .git, falling back to current working dir."""
    curr = (start or Path.cwd()).resolve()
    for parent in [curr, *curr.parents]:
        if (parent / CONFIG_FILE_NAME).is_file() or (parent / ".git").exists():
            return parent
    return curr


def get_dot_devsnap_path(root: Optional[Path] = None) -> Path:
    base = root or find_project_root()
    return base / DOT_DEVSNAP_DIR
