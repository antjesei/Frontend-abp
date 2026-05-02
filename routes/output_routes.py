"""
output_routes.py
----------------
Blueprint für Output-Dateien der Tools.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, send_file, url_for

from core import db
from core.env_manager import read_env

bp = Blueprint("output_routes", __name__, url_prefix="/tool")

# Bekannte Output-Verzeichnisse pro Tool-ID
OUTPUT_DIR_OVERRIDES = {
    "transkription-document-handling": None,  # aus .env OUTPUT_DIR, Fallback output/
}


def _get_output_dir(tool: dict) -> Path | None:
    """Ermittelt das Output-Verzeichnis eines Tools."""
    tool_path = Path(tool["path"])

    # Aus .env lesen (OUTPUT_DIR)
    env = read_env(tool_path)
    output_dir_env = env.get("OUTPUT_DIR", "").strip()
    if output_dir_env:
        p = Path(output_dir_env)
        if not p.is_absolute():
            p = tool_path / output_dir_env
        if p.is_dir():
            return p

    # Fallback: output/ im Tool-Verzeichnis
    fallback = tool_path / "output"
    if fallback.is_dir():
        return fallback

    return None


def _list_output_files(output_dir: Path) -> list[dict]:
    """Listet alle Dateien im Output-Verzeichnis rekursiv auf (max 2 Ebenen)."""
    files = []
    try:
        for entry in sorted(output_dir.iterdir()):
            if entry.is_file():
                stat = entry.stat()
                files.append({
                    "name": entry.name,
                    "rel_path": entry.name,
                    "size": stat.st_size,
                    "size_str": _format_size(stat.st_size),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M"),
                    "full_path": str(entry),
                })
            elif entry.is_dir():
                # Einen Level tiefer schauen
                for subentry in sorted(entry.iterdir()):
                    if subentry.is_file():
                        stat = subentry.stat()
                        files.append({
                            "name": subentry.name,
                            "rel_path": f"{entry.name}/{subentry.name}",
                            "size": stat.st_size,
                            "size_str": _format_size(stat.st_size),
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%d.%m.%Y %H:%M"),
                            "full_path": str(subentry),
                        })
    except PermissionError:
        pass
    return files


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


@bp.route("/<tool_id>/output")
def output_view(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))

    output_dir = _get_output_dir(tool)
    files = _list_output_files(output_dir) if output_dir else []

    return render_template(
        "tool_output.html",
        tool=tool,
        output_dir=str(output_dir) if output_dir else None,
        files=files,
        page_title=f"{tool['display_name']} — Output",
    )


@bp.route("/<tool_id>/output/download/<path:filename>")
def output_download(tool_id: str, filename: str):
    tool = db.get_tool(tool_id)
    if not tool:
        abort(404)

    output_dir = _get_output_dir(tool)
    if not output_dir:
        abort(404)

    file_path = output_dir / filename
    # Sicherheitscheck: Datei muss innerhalb output_dir sein
    try:
        file_path.resolve().relative_to(output_dir.resolve())
    except ValueError:
        abort(403)

    if not file_path.is_file():
        abort(404)

    return send_file(str(file_path), as_attachment=True)


@bp.route("/<tool_id>/output/open-folder", methods=["POST"])
def output_open_folder(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        abort(404)

    output_dir = _get_output_dir(tool)
    if not output_dir or not output_dir.is_dir():
        flash("Output-Verzeichnis nicht gefunden.", "error")
        return redirect(url_for("output_routes.output_view", tool_id=tool_id))

    try:
        subprocess.Popen(["explorer.exe", str(output_dir)])
    except Exception as e:
        flash(f"Konnte Ordner nicht öffnen: {e}", "error")

    return redirect(url_for("output_routes.output_view", tool_id=tool_id))
