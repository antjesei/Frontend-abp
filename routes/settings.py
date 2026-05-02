"""
settings.py
-----------
Blueprint für die Einstellungen-Seite.
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import db
from core.tool_detector import scan_tools

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/")
def settings_view():
    tools = db.get_all_tools(visible_only=False)
    return render_template(
        "settings.html",
        tools=tools,
        page_title="Einstellungen",
    )


@bp.route("/tool/<tool_id>", methods=["POST"])
def tool_save(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("settings.settings_view"))

    display_name = request.form.get("display_name", tool["display_name"]).strip()
    visible = 1 if request.form.get("visible") else 0
    port_raw = request.form.get("port", "").strip()
    port = int(port_raw) if port_raw.isdigit() else tool.get("port")
    description = request.form.get("description", "").strip() or None

    db.update_tool_settings(tool_id, display_name, visible, port, description)
    flash(f"Einstellungen für '{display_name}' gespeichert.", "success")
    return redirect(url_for("settings.settings_view"))


@bp.route("/rescan", methods=["POST"])
def rescan():
    found = scan_tools()
    count = 0
    for t in found:
        db.upsert_tool(t)
        count += 1
    flash(f"Scan abgeschlossen: {count} Tools gefunden.", "success")
    return redirect(url_for("settings.settings_view"))
