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


@bp.route("/<tool_id>/meetings")
def list_meetings(tool_id: str):
    """Gibt die letzten 20 Fireflies-Meetings als JSON zurück."""
    tool = db.get_tool(tool_id)
    if not tool:
        return jsonify({"error": "Tool nicht gefunden"}), 404

    python_exe = get_python_exe(Path(tool["path"]))
    try:
        result = subprocess.run(
            [python_exe, "main.py", "--list-json"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=tool["path"], timeout=30,
        )
        if result.returncode != 0:
            return jsonify({"error": result.stderr or "Fehler beim Laden"}), 500
        meetings = json.loads(result.stdout)
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
