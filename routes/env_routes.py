"""
env_routes.py
-------------
Blueprint für .env-Verwaltung der Tools.
"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from core import db
from core.env_manager import is_sensitive, read_env, read_env_example, write_env

bp = Blueprint("env_routes", __name__, url_prefix="/tool")


@bp.route("/<tool_id>/env", methods=["GET"])
def env_view(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))

    # Keys aus .env.example (definiert welche Felder angezeigt werden)
    example_keys = read_env_example(tool["path"])
    # Aktuelle Werte aus .env
    current_values = read_env(tool["path"])

    # Felder zusammenbauen: Example-Keys zuerst, dann ggf. extra Keys aus .env
    all_keys: dict[str, str] = {}
    for key in example_keys:
        all_keys[key] = current_values.get(key, "")
    for key, value in current_values.items():
        if key not in all_keys:
            all_keys[key] = value

    fields = [
        {
            "key": key,
            "value": value,
            "sensitive": is_sensitive(key),
        }
        for key, value in all_keys.items()
    ]

    return render_template(
        "tool_env.html",
        tool=tool,
        fields=fields,
        page_title=f"{tool['display_name']} — .env",
    )


@bp.route("/<tool_id>/env", methods=["POST"])
def env_save(tool_id: str):
    tool = db.get_tool(tool_id)
    if not tool:
        flash(f"Tool '{tool_id}' nicht gefunden.", "error")
        return redirect(url_for("dashboard.index"))

    # Alle Felder aus dem Formular lesen
    env_dict: dict[str, str] = {}
    for key, value in request.form.items():
        if key.startswith("env_"):
            actual_key = key[4:]  # "env_" prefix entfernen
            env_dict[actual_key] = value

    try:
        write_env(tool["path"], env_dict)
        flash(".env erfolgreich gespeichert.", "success")
    except Exception as e:
        flash(f"Fehler beim Speichern: {e}", "error")

    return redirect(url_for("env_routes.env_view", tool_id=tool_id))
