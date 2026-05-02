"""
tool_actions.py
---------------
Blueprint für Tool-Start/Stop und Logs.
"""
from __future__ import annotations

import time

from flask import Blueprint, Response, redirect, render_template, url_for, flash, stream_with_context

from core import db, tool_runner

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
