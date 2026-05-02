"""
env_manager.py
--------------
Liest und schreibt .env-Dateien für Tools.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

SENSITIVE_PATTERN = re.compile(
    r"KEY|TOKEN|SECRET|PASSWORD|APIKEY|API_KEY", re.IGNORECASE
)


def is_sensitive(key: str) -> bool:
    """Gibt True zurück wenn der Schlüssel sensibel wirkt."""
    return bool(SENSITIVE_PATTERN.search(key))


def read_env(tool_path: str | Path) -> dict[str, str]:
    """Liest .env aus tool_path. Gibt leeres Dict zurück wenn nicht vorhanden."""
    env_file = Path(tool_path) / ".env"
    result: dict[str, str] = {}
    if not env_file.exists():
        return result
    try:
        content = env_file.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, value = stripped.partition("=")
                key = key.strip()
                value = value.strip()
                # Anführungszeichen entfernen
                if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                if key:
                    result[key] = value
    except Exception:
        pass
    return result


def read_env_example(tool_path: str | Path) -> dict[str, str]:
    """Liest .env.example aus tool_path. Gibt dict mit leeren Werten zurück."""
    env_file = Path(tool_path) / ".env.example"
    result: dict[str, str] = {}
    if not env_file.exists():
        return result
    try:
        content = env_file.read_text(encoding="utf-8", errors="ignore")
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                if key:
                    result[key] = ""
    except Exception:
        pass
    return result


def write_env(tool_path: str | Path, env_dict: dict[str, str]) -> None:
    """Schreibt .env-Datei atomisch. Erhält Kommentarzeilen soweit möglich."""
    env_file = Path(tool_path) / ".env"

    # Bestehende Kommentarzeilen lesen
    existing_lines: list[str] = []
    if env_file.exists():
        try:
            existing_lines = env_file.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            existing_lines = []

    # Neue Datei aufbauen: Kommentare beibehalten, bekannte Keys aktualisieren
    written_keys: set[str] = set()
    new_lines: list[str] = []

    for line in existing_lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append("")
            continue
        if stripped.startswith("#"):
            new_lines.append(line)
            continue
        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key in env_dict:
                value = env_dict[key]
                new_lines.append(f"{key}={value}")
                written_keys.add(key)
            # Key nicht mehr in env_dict → weglassen (gelöscht vom Nutzer)
        # Sonstige Zeilen beibehalten
        else:
            new_lines.append(line)

    # Neue Keys (die noch nicht in der Datei waren) am Ende anhängen
    for key, value in env_dict.items():
        if key not in written_keys:
            new_lines.append(f"{key}={value}")

    content = "\n".join(new_lines) + "\n"

    # Atomisch schreiben: temp file + os.replace
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=str(env_file.parent), suffix=".tmp", prefix=".env_"
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, str(env_file))
    except Exception:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
        raise
