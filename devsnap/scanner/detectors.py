from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from devsnap.config import (
    DevSnapConfig,
    FirebaseEmulatorsConfig,
    PostgresConfig,
    ServiceConfig,
    StateConfig,
)
from devsnap.scanner.ast_analyzer import IGNORE_DIRS


def detect_env_files(root: Path) -> List[str]:
    found: List[str] = []
    # Search common env file patterns
    for path in root.rglob(".env*"):
        if not path.is_file():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        # Exclude example or sample templates from active env
        if "example" in rel or "sample" in rel or "template" in rel:
            continue
        found.append(rel)

    if not found and (root / ".env").exists():
        found.append(".env")
    elif not found:
        found.append(".env")
    return sorted(list(set(found)))


def detect_sqlite_databases(root: Path) -> List[str]:
    databases: List[str] = []
    for ext in ["*.db", "*.sqlite", "*.sqlite3"]:
        for path in root.rglob(ext):
            if not path.is_file():
                continue
            if any(part in IGNORE_DIRS for part in path.parts):
                continue
            databases.append(path.relative_to(root).as_posix())
    return sorted(databases)


def detect_firebase_config(root: Path) -> Optional[FirebaseEmulatorsConfig]:
    fb_file = root / "firebase.json"
    if fb_file.is_file():
        ports: List[int] = [4000, 8080, 9099]
        try:
            with open(fb_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                emulators = data.get("emulators", {})
                detected_ports: List[int] = []
                for em_name, em_val in emulators.items():
                    if isinstance(em_val, dict) and "port" in em_val:
                        detected_ports.append(int(em_val["port"]))
                if detected_ports:
                    ports = sorted(list(set(detected_ports)))
        except Exception:
            pass
        return FirebaseEmulatorsConfig(config="firebase.json", ports=ports)
    return None


def detect_credential_files(root: Path) -> Dict[str, str]:
    credentials: Dict[str, str] = {}
    for path in root.rglob("*service-account*.json"):
        if path.is_file() and not any(part in IGNORE_DIRS for part in path.parts):
            credentials["GOOGLE_APPLICATION_CREDENTIALS"] = path.relative_to(root).as_posix()
            break
    return credentials


def detect_services_and_state(root: Path) -> tuple[StateConfig, Dict[str, ServiceConfig]]:
    state = StateConfig()
    services: Dict[str, ServiceConfig] = {}

    # Check SQLite
    sqlite_dbs = detect_sqlite_databases(root)
    if sqlite_dbs:
        state.sqlite = sqlite_dbs

    # Check Firebase
    fb_config = detect_firebase_config(root)
    if fb_config:
        state.firebase_emulators = fb_config

    # Check Backend (Python / Node)
    has_fastapi = False
    has_flask = False
    has_django = False

    pyproject = root / "pyproject.toml"
    requirements = root / "requirements.txt"
    py_text = ""
    if pyproject.is_file():
        py_text += pyproject.read_text(encoding="utf-8", errors="ignore")
    if requirements.is_file():
        py_text += requirements.read_text(encoding="utf-8", errors="ignore")

    if "fastapi" in py_text.lower():
        has_fastapi = True
    elif "flask" in py_text.lower():
        has_flask = True
    elif "django" in py_text.lower():
        has_django = True

    # Detect package.json services
    package_json = root / "package.json"
    mobile_package_json = root / "mobile" / "package.json"
    frontend_package_json = root / "frontend" / "package.json"
    client_package_json = root / "client" / "package.json"

    # Configure backend service
    backend_port = 8000
    if has_fastapi:
        services["backend"] = ServiceConfig(
            cmd="uvicorn app.main:app --reload --port 8000",
            port=backend_port,
            tunnel=True,
        )
    elif has_flask:
        services["backend"] = ServiceConfig(
            cmd="flask run --port 8000",
            port=backend_port,
            tunnel=True,
        )
    elif has_django:
        services["backend"] = ServiceConfig(
            cmd="python manage.py runserver 8000",
            port=backend_port,
            tunnel=True,
        )

    # Detect mobile / Expo
    has_expo = False
    expo_cwd: Optional[str] = None
    if mobile_package_json.is_file():
        m_txt = mobile_package_json.read_text(encoding="utf-8", errors="ignore")
        if "expo" in m_txt:
            has_expo = True
            expo_cwd = "./mobile"
    elif (root / "app.json").is_file() or (package_json.is_file() and "expo" in package_json.read_text(encoding="utf-8", errors="ignore")):
        has_expo = True
        expo_cwd = None

    if has_expo:
        services["mobile"] = ServiceConfig(
            cmd="npx expo start --tunnel",
            cwd=expo_cwd,
            inject_env={
                "EXPO_PUBLIC_API_URL": "$services.backend.tunnel_url",
            },
        )
    elif frontend_package_json.is_file() or client_package_json.is_file():
        fe_dir = "./frontend" if frontend_package_json.is_file() else "./client"
        services["frontend"] = ServiceConfig(
            cmd="npm run dev",
            cwd=fe_dir,
            inject_env={
                "VITE_API_URL": "$services.backend.tunnel_url",
                "NEXT_PUBLIC_API_URL": "$services.backend.tunnel_url",
            },
        )

    return state, services


def build_scanned_config(root: Path) -> DevSnapConfig:
    env_files = detect_env_files(root)
    credentials = detect_credential_files(root)
    state, services = detect_services_and_state(root)

    return DevSnapConfig(
        version="1.0",
        collaborators=[],
        env_files=env_files,
        credential_files=credentials,
        state=state,
        services=services,
    )
