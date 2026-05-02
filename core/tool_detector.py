"""
tool_detector.py
----------------
Scannt das AI Projects-Verzeichnis und klassifiziert alle Tools.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime, timezone

PROJECTS_ROOT = Path(r"C:\Users\abau\AI Projects")
FRONTEND_DIR = PROJECTS_ROOT / "Frontend"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _classify_tool(tool_path: Path) -> dict:
    """Gibt ein Tool-Dict zurück für ein Verzeichnis."""
    name = tool_path.name
    tool_id = _slug(name)
    now = datetime.now(timezone.utc).isoformat()

    has_app_py = (tool_path / "app.py").exists()
    has_main_py = (tool_path / "main.py").exists()
    has_requirements = (tool_path / "requirements.txt").exists()
    has_venv = (tool_path / ".venv").is_dir()

    # .env.example lesen
    env_example_keys: list[str] = []
    env_example_path = tool_path / ".env.example"
    if env_example_path.exists():
        content = _read_file_safe(env_example_path)
        for line in content.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key = line.split("=", 1)[0].strip()
                if key:
                    env_example_keys.append(key)

    # Typ bestimmen
    req_content = ""
    if has_requirements:
        req_content = _read_file_safe(tool_path / "requirements.txt").lower()

    if has_app_py and "flask" in req_content:
        tool_type = "web"
        default_port = 5000
    elif has_main_py and not has_app_py:
        tool_type = "cli"
        default_port = None
    elif has_app_py and not ("flask" in req_content):
        # app.py but no flask in requirements — could still be flask if imported
        app_content = _read_file_safe(tool_path / "app.py").lower()
        if "from flask" in app_content or "import flask" in app_content:
            tool_type = "web"
            default_port = 5000
        else:
            tool_type = "placeholder"
            default_port = None
    else:
        tool_type = "placeholder"
        default_port = None

    return {
        "id": tool_id,
        "display_name": name,
        "path": str(tool_path),
        "type": tool_type,
        "port": default_port,
        "has_venv": has_venv,
        "env_example_keys": env_example_keys,
        "detected_at": now,
        "last_seen_at": now,
    }


def scan_tools() -> list[dict]:
    """Scannt PROJECTS_ROOT und gibt Liste von Tool-Dicts zurück."""
    tools = []
    if not PROJECTS_ROOT.is_dir():
        return tools

    for entry in sorted(PROJECTS_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        # Eigenes Frontend-Verzeichnis überspringen
        if entry.resolve() == FRONTEND_DIR.resolve():
            continue
        # Versteckte Verzeichnisse überspringen
        if entry.name.startswith("."):
            continue
        tools.append(_classify_tool(entry))

    return tools
