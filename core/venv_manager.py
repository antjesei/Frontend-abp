"""
venv_manager.py
---------------
Verwaltet virtuelle Python-Umgebungen der Tools.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Generator


def get_python_exe(tool_path: str | Path) -> str:
    """Gibt den Pfad zum Python-Executable im .venv zurück, oder 'python' als Fallback."""
    venv_python = Path(tool_path) / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return "python"


def get_venv_info(tool_path: str | Path) -> dict:
    """Gibt Infos über das .venv zurück: has_venv, python_version, packages."""
    tool_path = Path(tool_path)
    venv_dir = tool_path / ".venv"
    result = {
        "has_venv": venv_dir.is_dir(),
        "python_version": None,
        "packages": [],
    }

    if not result["has_venv"]:
        return result

    python_exe = get_python_exe(tool_path)

    # Python-Version abfragen
    try:
        proc = subprocess.run(
            [python_exe, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        version_output = proc.stdout.strip() or proc.stderr.strip()
        result["python_version"] = version_output.replace("Python ", "").strip()
    except Exception:
        pass

    # Installierte Pakete abfragen
    try:
        proc = subprocess.run(
            [python_exe, "-m", "pip", "list", "--format=json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            import json
            packages = json.loads(proc.stdout)
            result["packages"] = [
                {"name": p.get("name", ""), "version": p.get("version", "")}
                for p in packages
            ]
    except Exception:
        pass

    return result


def install_requirements(tool_path: str | Path) -> Generator[str, None, None]:
    """Generator: yielded zeilenweise Output von pip install -r requirements.txt."""
    tool_path = Path(tool_path)
    requirements_file = tool_path / "requirements.txt"

    if not requirements_file.exists():
        yield "FEHLER: requirements.txt nicht gefunden."
        return

    python_exe = get_python_exe(tool_path)

    # Sicherstellen dass pip aktuell ist
    try:
        proc = subprocess.Popen(
            [python_exe, "-m", "pip", "install", "-r", str(requirements_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(tool_path),
        )
        if proc.stdout:
            for line in proc.stdout:
                yield line.rstrip("\n\r")
        proc.wait()
        if proc.returncode == 0:
            yield "Installation erfolgreich abgeschlossen."
        else:
            yield f"FEHLER: pip beendete sich mit Code {proc.returncode}."
    except Exception as e:
        yield f"FEHLER beim Starten von pip: {e}"
