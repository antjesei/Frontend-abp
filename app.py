"""
app.py
------
abp Toolboard — Flask-Hauptanwendung auf Port 8080.
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, g
from core.db import init_db, upsert_tool, get_all_tools, upsert_cli_spec
from core.tool_detector import scan_tools
from core import tool_runner
from routes.dashboard import bp as dashboard_bp
from routes.tool_actions import bp as tool_actions_bp
from routes.env_routes import bp as env_bp
from routes.output_routes import bp as output_bp
from routes.venv_routes import bp as venv_bp
from routes.settings import bp as settings_bp

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "abp-toolboard-dev-secret-2024")

# Blueprints registrieren
app.register_blueprint(dashboard_bp)
app.register_blueprint(tool_actions_bp)
app.register_blueprint(env_bp)
app.register_blueprint(output_bp)
app.register_blueprint(venv_bp)
app.register_blueprint(settings_bp)


@app.context_processor
def inject_sidebar_tools():
    """Stellt sidebar_tools für alle Templates bereit."""
    tools = get_all_tools(visible_only=True)
    for tool in tools:
        tool["status"] = tool_runner.get_status(tool["id"])
    return {"sidebar_tools": tools}


if __name__ == "__main__":
    init_db()

    # Initialer Scan
    for t in scan_tools():
        upsert_tool(t)

    # CLI-Arg-Specs für bekannte Tools vorbelegen
    all_tools = get_all_tools()
    tool_ids = {t["id"] for t in all_tools}

    if "transkription-document-handling" in tool_ids:
        upsert_cli_spec(
            "transkription-document-handling",
            "--last",
            "Zeitraum (z.B. 24h, 3d, 2w)",
            "string",
            "7d",
        )
        upsert_cli_spec(
            "transkription-document-handling",
            "--since",
            "Seit Datum (YYYY-MM-DD)",
            "date",
            "",
        )
        upsert_cli_spec(
            "transkription-document-handling",
            "meeting_id",
            "Meeting-ID (einzelnes Meeting)",
            "string",
            "",
        )

    print("=" * 52)
    print("  abp Toolboard")
    print("  http://127.0.0.1:8080")
    print("=" * 52)

    app.run(host="127.0.0.1", port=8080, debug=False)
