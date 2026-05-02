"""
tool_actions.py
---------------
Blueprint für Tool-Start/Stop und Logs.
"""
from __future__ import annotations

import json
import re
import subprocess
import time

from flask import Blueprint, Response, redirect, render_template, url_for, flash, stream_with_context, jsonify, request

from core import db, tool_runner
from core.venv_manager import get_python_exe
from pathlib import Path

bp = Blueprint("tool_actions", __name__, url_prefix="/tool")


@bp.route("/<tool_id>")
def tool_detail(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))
    status = tool_runner.get_status(tool_id)
    cli_specs = db.get_cli_specs(tool_id)
    logs = tool_runner.get_logs(tool_id)
    return render_template(
        "tool_detail.html",
        tool=tool,
        status=status,
        cli_specs=cli_specs,
        logs=logs,
        page_title=tool["display_name"],
    )


@bp.route("/<tool_id>/start", methods=["POST"])
def start(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))
    success, error_msg = tool_runner.start_tool(tool)
    if success:
        flash(f"{tool['display_name']} wird gestartet.", "success")
    else:
        flash(f"Fehler beim Starten: {error_msg}", "error")
    return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))


@bp.route("/<tool_id>/stop", methods=["POST"])
def stop(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))
    success = tool_runner.stop_tool(tool_id)
    if success:
        flash(f"{tool['display_name']} gestoppt.", "success")
    else:
        flash("Fehler beim Stoppen.", "error")
    return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))


@bp.route("/<tool_id>/logs/stream")
def logs_stream(tool_id: str):
    """SSE-Endpoint für Live-Logs."""
    def generate():
        sent_count = 0
        # Erst alle vorhandenen Logs schicken
        existing = tool_runner.get_logs(tool_id)
        for line in existing:
            yield f"data: {line}\n\n"
        sent_count = len(existing)

        # Dann auf neue Zeilen warten
        max_iterations = 600  # max 5 Minuten bei 0.5s Sleep
        for _ in range(max_iterations):
            time.sleep(0.5)
            current = tool_runner.get_logs(tool_id)
            if len(current) > sent_count:
                for line in current[sent_count:]:
                    yield f"data: {line}\n\n"
                sent_count = len(current)

            status = tool_runner.get_status(tool_id)
            if status in ("stopped", "failed"):
                time.sleep(0.5)
                # Noch letzte Zeilen schicken
                current = tool_runner.get_logs(tool_id)
                if len(current) > sent_count:
                    for line in current[sent_count:]:
                        yield f"data: {line}\n\n"
                yield "event: end\ndata: \n\n"
                return

        yield "event: end\ndata: timeout\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


_meetings_cache: dict[str, tuple[float, list]] = {}  # tool_id -> (timestamp, data)
_CACHE_TTL = 300  # 5 Minuten


def _sanitize(name: str) -> str:
    """Repliziert naming.sanitize_filename aus dem Transkriptions-Tool."""
    import re
    name = re.sub(r'\.(mp4|mov|avi|mkv|webm|m4v|mp3|wav|m4a)$', '', name.strip(), flags=re.IGNORECASE)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip().strip('.')
    name = re.sub(r'\s+', ' ', name)
    name = re.sub(r'_+', '_', name)
    return name or 'meeting'


def _get_downloaded_folder_names(tool: dict) -> set[str]:
    """Gibt die Menge der Ordnernamen zurück, die Transkriptions-Artefakte enthalten."""
    import os
    # OUTPUT_DIR aus .env des Tools laden
    output_dir = None
    env_path = Path(tool["path"]) / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("OUTPUT_DIR="):
                output_dir = line.split("=", 1)[1].strip()
                break
    if not output_dir:
        output_dir = str(Path(tool["path"]) / "output")

    artifact_suffixes = ("_transkr.docx", "_transkr.md", "_sum.docx", "_sum.md", "_audio.mp3")
    downloaded: set[str] = set()
    try:
        for entry in os.scandir(output_dir):
            if not entry.is_dir():
                continue
            for f in os.scandir(entry.path):
                if any(f.name.endswith(s) for s in artifact_suffixes):
                    downloaded.add(entry.name)
                    break
    except FileNotFoundError:
        pass
    return downloaded


@bp.route("/<tool_id>/meetings")
def list_meetings(tool_id: str):
    """Gibt Fireflies-Meetings als JSON zurück.
    ?filter=downloaded → nur bereits lokal heruntergeladene.
    """
    tool = db.get_tool(tool_id)
    if not tool:
        return jsonify({"error": "Tool nicht gefunden"}), 404

    only_downloaded = request.args.get("filter") == "downloaded"

    # Cache prüfen (nur für vollständige Liste)
    if not only_downloaded:
        cached = _meetings_cache.get(tool_id)
        if cached and (time.time() - cached[0]) < _CACHE_TTL:
            return jsonify(cached[1])

    python_exe = get_python_exe(Path(tool["path"]))
    try:
        result = subprocess.run(
            [python_exe, "main.py", "--list-json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=tool["path"], timeout=30,
        )
        err_text = (result.stderr or "").strip() or (result.stdout or "").strip()
        if result.returncode != 0:
            if "Rate-Limit" in err_text or "too_many_requests" in err_text or "retry" in err_text.lower():
                msg = next((l for l in err_text.splitlines() if "Rate-Limit" in l or "retry" in l.lower()), err_text)
                return jsonify({"error": msg}), 429
            return jsonify({"error": err_text or "Fehler beim Laden"}), 500

        meetings = json.loads(result.stdout)
        _meetings_cache[tool_id] = (time.time(), meetings)

        if only_downloaded:
            local_folders = _get_downloaded_folder_names(tool)
            meetings = [m for m in meetings if _sanitize(m["title"]) in local_folders]

        return jsonify(meetings)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Timeout beim Laden der Meetings"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _parse_picks(raw: str, max_n: int) -> list[int]:
    """Parst '1', '1,3,5', '1-5', '1-3,7,9-11' zu sortierter Liste (1-basiert)."""
    picks: set[int] = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            a, b = int(parts[0].strip()), int(parts[1].strip())
            if a > b:
                a, b = b, a
            picks.update(range(a, b + 1))
        else:
            picks.add(int(token))
    return sorted(p for p in picks if 1 <= p <= max_n)


@bp.route("/<tool_id>/run-picks", methods=["POST"])
def run_picks(tool_id: str):
    """Startet CLI-Tool für ausgewählte Meeting-IDs (Checkboxen oder Nummern)."""
    tool = db.get_tool(tool_id)
    if not tool:
        flash("Tool nicht gefunden.", "error")
        return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))

    # Ausgewählte IDs direkt (Checkboxen)
    selected_ids = request.form.getlist("meeting_id")

    # Alternativ: Nummernauswahl auflösen
    if not selected_ids:
        picks_raw = request.form.get("picks", "").strip()
        if picks_raw:
            python_exe = get_python_exe(Path(tool["path"]))
            try:
                result = subprocess.run(
                    [python_exe, "main.py", "--list-json"],
                    capture_output=True, text=True, encoding="utf-8",
                    errors="replace", cwd=tool["path"], timeout=30,
                )
                meetings = json.loads(result.stdout)
                indices = _parse_picks(picks_raw, len(meetings))
                selected_ids = [meetings[i - 1]["id"] for i in indices]
            except Exception as e:
                flash(f"Fehler beim Auflösen der Auswahl: {e}", "error")
                return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))

    if not selected_ids:
        flash("Keine Meetings ausgewählt.", "error")
        return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))

    success, err = tool_runner.start_tool_with_ids(tool, selected_ids)
    if success:
        flash(f"{len(selected_ids)} Meeting(s) werden heruntergeladen.", "success")
    else:
        flash(f"Fehler: {err}", "error")
    return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))


@bp.route("/<tool_id>/delete-recordings", methods=["POST"])
def delete_recordings(tool_id: str):
    """Löscht ausgewählte Fireflies-Aufnahmen dauerhaft."""
    tool = db.get_tool(tool_id)
    if not tool:
        flash("Tool nicht gefunden.", "error")
        return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))

    selected_ids = request.form.getlist("meeting_id")
    if not selected_ids:
        flash("Keine Aufnahmen ausgewählt.", "error")
        return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))

    success, err = tool_runner.start_tool_delete_ids(tool, selected_ids)
    if success:
        flash(f"{len(selected_ids)} Aufnahme(n) werden gelöscht. Fortschritt im Logs-Tab.", "success")
    else:
        flash(f"Fehler: {err}", "error")
    return redirect(url_for("tool_actions.tool_detail", tool_id=tool_id))
