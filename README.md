# DevSnap ⚡️

> Git branches your code and Docker branches your binaries—**DevSnap** branches your running application state, secrets, and local network tunnels in one command for both human teammates and AI coding agents.

---

## 1. Problem: The 3 Layers of Dev Friction

Reproducible dev tools (Docker, Dev Containers, Nix, Mise) only solve **Layer 1: Binary & Runtime Installation**. When a developer or autonomous AI coding agent clones a repository, the application still fails to run because of **Layer 2** and **Layer 3**:

| Layer | Scope | Real-World Pain Point | DevSnap Solution |
| :--- | :--- | :--- | :--- |
| **Layer 1: Binaries** | OS packages, Node, Python, CLIs | Version mismatches (`Node 18` vs `20`) | Delegated to existing tools (`mise` / `uv` / `devcontainer.json`). |
| **Layer 2: State & Secrets** | `.env` files, service credentials, SQLite / Firebase Emulator rows | Teammates pull code and crash on missing API keys or render empty screens due to an unseeded DB. | **Zero-Account SSH Encryption + Git State Snapshots:** Encrypts `.env` files and hot DB backups against GitHub collaborators' public SSH keys (`age -R`) and syncs via Git plumbing refs (`refs/devsnap/latest`). |
| **Layer 3: Network & Tunnels** | Mobile testing (Expo Go), corporate/university Wi-Fi (`eduroam`) | Expo `--tunnel` only tunnels Metro (`:8081`), leaving local backend (`:8000`) unreachable from physical phones. | **Auto-Tunnel & Dynamic Env Injection:** Spawns ephemeral HTTPS tunnels (`cloudflared`) for backends and injects the live URLs into mobile/frontend processes at boot. |

---

## 2. Installation & Quickstart

```bash
# Install DevSnap using uv or pip
pip install devsnap
# or run directly with uvx
uvx devsnap --help
```

### 1. Initialize Project (`devsnap init`)
Scans repository AST, configuration files, detects frameworks, extracts `.env` keys, and fetches collaborator public SSH keys directly from GitHub:

```bash
devsnap init --collaborator octocat --collaborator teammate-handle
```

This creates:
- `devsnap.json`: Declarative topology of services, state files, and tunnels.
- `.devsnap/recipients.txt`: Collaborators' public SSH keys fetched from `https://github.com/{username}.keys`.

### 2. Capture & Encrypt State (`devsnap push`)
Captures a hot-backup of your local SQLite database, packages credentials, encrypts with `age`, and stores to an isolated Git ref:

```bash
devsnap push -m "Seeded demo users & Stripe test keys"
```

*Never touches or modifies your working Git branch or staging index.*

### 3. Decrypt & Hydrate on Another Machine (`devsnap pull`)
On a teammate's laptop or AI agent environment:

```bash
devsnap pull
```

Fetches the snapshot ref, decrypts using your local private SSH key (`~/.ssh/id_ed25519`), restores `.env` files, and hydrates the SQLite database in under 3 seconds.

### 4. Multiplexed Boot & Auto-Tunneling (`devsnap up --share`)
Boots your backend, spawns a Cloudflare Quick Tunnel (`*.trycloudflare.com`), programmatically captures the live HTTPS URL, injects `EXPO_PUBLIC_API_URL`, and starts Expo:

```bash
devsnap up --share
```

```text
14:05:00 [backend] Booting: uvicorn app.main:app --port 8000
14:05:01 [tunnel]  ✓ Live Tunnel Ready: https://orange-tiger-1234.trycloudflare.com -> localhost:8000
14:05:02 [mobile]  Injecting EXPO_PUBLIC_API_URL=https://orange-tiger-1234.trycloudflare.com
14:05:02 [mobile]  Metro waiting on exp://192.168.1.10:8081
```

Physical phones on cellular or isolated Wi-Fi can now scan the Expo QR code and reach your laptop's backend!

---

## 3. AI Coding Agent Control Plane (`devsnap mcp`)

DevSnap includes a built-in FastMCP server exposing local environment topology, live log streams, and 1-click state resets directly to Cursor and Claude Code.

### Cursor Configuration (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "devsnap": {
      "command": "devsnap",
      "args": ["mcp"]
    }
  }
}
```

### Claude Desktop Configuration (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "devsnap": {
      "command": "devsnap",
      "args": ["mcp"]
    }
  }
}
```

### Exposed MCP Tools
1. `get_env_topology()`: Returns active services, live ports, active tunnel URLs, and missing `.env` keys.
2. `restore_state_snapshot()`: Resets corrupted database records back to the clean snapshot in <1s between test runs.
3. `read_service_logs(service, lines)`: Streams recent stdout/stderr buffers from backend or tunnel.
4. `verify_env_schema()`: Validates that all env keys discovered in source code exist in active `.env` files.

---

## 4. Configuration Schema (`devsnap.json`)

```json
{
  "version": "1.0",
  "collaborators": ["octocat", "teammate"],
  "env_files": [".env", "mobile/.env"],
  "credential_files": {
    "GOOGLE_APPLICATION_CREDENTIALS": "service-account.json"
  },
  "state": {
    "sqlite": ["backend/app.db"],
    "firebase_emulators": {
      "config": "firebase.json",
      "ports": [4000, 8080, 9099]
    }
  },
  "services": {
    "backend": {
      "cmd": "uvicorn app.main:app --reload --port 8000",
      "port": 8000,
      "tunnel": true
    },
    "mobile": {
      "cmd": "npx expo start --tunnel",
      "cwd": "./mobile",
      "inject_env": {
        "EXPO_PUBLIC_API_URL": "$services.backend.tunnel_url"
      }
    }
  }
}
```

---

## 5. Architecture & Cryptography Details

- **Zero Accounts**: No external accounts, AWS S3 buckets, or proprietary SaaS dashboards.
- **Identity via GitHub**: Public keys fetched from `https://github.com/{username}.keys`.
- **Encryption**: Authenticated file encryption using `age` targeting multiple recipient keys (`age -R .devsnap/recipients.txt`).
- **Transport via Git Plumbing**: Uses `git hash-object -w`, `git mktree`, `git commit-tree`, and `git update-ref refs/devsnap/latest` to store state blobs on detached refs without modifying your Git working tree or commits.
