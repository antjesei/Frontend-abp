"""
dashboard.py
------------
Haupt-Dashboard Blueprint.
"""
from __future__ import annotations

from flask import Blueprint, render_template

from core import db, tool_runner

bp = Blueprint("dashboard", __name__, url_prefix="/")


@bp.route("/")
def index():
    tools = db.get_all_tools(visible_only=True)
    for tool in tools:
        tool["status"] = tool_runner.get_status(tool["id"])
    return render_template("dashboard.html", tools=tools, page_title="Dashboard")
