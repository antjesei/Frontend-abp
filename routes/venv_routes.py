"""
venv_routes.py
--------------
Blueprint für Venv-Verwaltung der Tools.
"""
from __future__ import annotations

from flask import Blueprint, Response, flash, redirect, render_template, url_for, stream_with_context

from core import db
from core.venv_manager import get_venv_info, install_requirements

bp = Blueprint("venv_routes", __name__, url_prefix="/tool")


@bp.route("/<tool_id>/venv")
def venv_view(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))

    venv_info = get_venv_info(tool["path"])

    return render_template(
        "tool_venv.html",
        tool=tool,
        venv_info=venv_info,
        page_title=f"{tool['display_name']} — Venv",
    )


@bp.route("/<tool_id>/venv/install/stream")
def venv_install_stream(tool_id: str):
    """SSE-Stream für pip install."""
    tool = db.get_tool(tool_id)
    if not tool:
        def err_gen():
            yield "data: Tool nicht gefunden.\n\n"
            yield "event: end\ndata: \n\n"
        return Response(stream_with_context(err_gen()), mimetype="text/event-stream")

    def generate():
        for line in install_requirements(tool["path"]):
            yield f"data: {line}\n\n"
        yield "event: end\ndata: \n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
