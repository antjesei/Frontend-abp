"""
tool_runner.py
--------------
Verwaltet laufende Subprozesse der Tools.
"""
from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import STDOUT

import psutil

from core.venv_manager import get_python_exe


@dataclass
class RunningProcess:
    tool_id: str
    pid: int
    process: subprocess.Popen
    log_buffer: deque = field(default_factory=lambda: deque(maxlen=1000))
    status: str = "starting"  # starting | running | stopped | failed


active_runs: dict[str, RunningProcess] = {}


def _check_port_free(port: int) -> bool:
    """Gibt True zurück wenn der Port nicht belegt ist."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.settimeout(1)
            result = s.connect_ex(("127.0.0.1", port))
            return result != 0  # 0 = Verbindung erfolgreich = Port belegt
        except Exception:
            return True


def _log_reader(rp: RunningProcess) -> None:
    """Liest stdout/stderr des Prozesses in den log_buffer."""
    first_output = True
    try:
        if rp.process.stdout:
            for raw_line in rp.process.stdout:
                line = raw_line.rstrip("\n\r")
                rp.log_buffer.append(line)
                if first_output and rp.status == "starting":
                    rp.status = "running"
                    first_output = False
    except Exception as e:
        rp.log_buffer.append(f"[log reader error: {e}]")

    # Prozess hat geendet
    try:
        rp.process.wait(timeout=5)
    except Exception:
        pass

    if rp.status not in ("stopped", "failed"):
        ret = rp.process.returncode
        if ret is not None and ret != 0:
            rp.status = "failed"
            rp.log_buffer.append(f"[Prozess beendet mit Code {ret}]")
        else:
            rp.status = "stopped"
            rp.log_buffer.append("[Prozess beendet]")


def start_tool(tool: dict) -> tuple[bool, str]:
    """Startet ein Tool als Subprocess. Gibt (success, error_message) zurück."""
    tool_id = tool["id"]

    # Bereits laufend?
    if tool_id in active_runs:
        rp = active_runs[tool_id]
        if rp.status in ("running", "starting"):
            return False, "Tool läuft bereits."
        else:
            # Alten Eintrag bereinigen
            del active_runs[tool_id]

    tool_path = Path(tool["path"])
    tool_type = tool.get("type", "placeholder")
    port = tool.get("port")

    if tool_type == "placeholder":
        return False, "Placeholder-Tools können nicht gestartet werden."

    # Port-Check für Web-Tools
    if tool_type == "web" and port:
        if not _check_port_free(port):
            return False, f"Port {port} ist bereits belegt."

    # Python-Executable ermitteln
    python_exe = get_python_exe(tool_path)

    # Startkommando bestimmen
    start_cmd = tool.get("start_cmd")
    if start_cmd:
        cmd = start_cmd
        use_shell = True
    elif tool_type == "web":
        cmd = [python_exe, "app.py"]
        use_shell = False
    elif tool_type == "cli":
        cmd = [python_exe, "main.py"]
        use_shell = False
    else:
        return False, "Unbekannter Tool-Typ."

    # Umgebungsvariablen
    env = os.environ.copy()
    if tool_type == "web" and port:
        env["PORT"] = str(port)

    try:
        if use_shell:
            proc = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(tool_path),
                env=env,
            )
        else:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(tool_path),
                env=env,
            )
    except Exception as e:
        return False, f"Konnte Prozess nicht starten: {e}"

    rp = RunningProcess(
        tool_id=tool_id,
        pid=proc.pid,
        process=proc,
        status="starting",
    )
    rp.log_buffer.append(f"[Gestartet: PID {proc.pid}]")
    active_runs[tool_id] = rp

    # Log-Reader-Thread starten
    t = threading.Thread(target=_log_reader, args=(rp,), daemon=True)
    t.start()

    # Kurz warten damit Status gesetzt wird
    time.sleep(0.3)
    # Prüfen ob Prozess sofort beendet wurde
    if proc.poll() is not None and rp.status == "starting":
        rp.status = "failed"

    return True, ""


def stop_tool(tool_id: str) -> bool:
    """Stoppt ein laufendes Tool. Gibt True bei Erfolg zurück."""
    rp = active_runs.get(tool_id)
    if not rp:
        return False

    try:
        parent = psutil.Process(rp.pid)
        # Kindprozesse zuerst beenden
        children = parent.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass

        parent.terminate()

        # 3 Sekunden warten
        try:
            parent.wait(timeout=3)
        except psutil.TimeoutExpired:
            # Dann kill
            try:
                parent.kill()
            except psutil.NoSuchProcess:
                pass
            for child in children:
                try:
                    child.kill()
                except psutil.NoSuchProcess:
                    pass

        rp.status = "stopped"
        rp.log_buffer.append("[Prozess gestoppt]")
        return True

    except psutil.NoSuchProcess:
        rp.status = "stopped"
        return True
    except Exception as e:
        rp.log_buffer.append(f"[Stop-Fehler: {e}]")
        return False


def get_status(tool_id: str) -> str:
    """Gibt den Status eines Tools zurück: running | stopped | starting | failed."""
    rp = active_runs.get(tool_id)
    if not rp:
        return "stopped"

    # Prozess-Status aktualisieren wenn nötig
    if rp.status in ("running", "starting"):
        if rp.process.poll() is not None:
            ret = rp.process.returncode
            if ret is not None and ret != 0:
                rp.status = "failed"
            else:
                rp.status = "stopped"

    return rp.status


def get_logs(tool_id: str) -> list[str]:
    """Gibt den aktuellen log_buffer als Liste zurück."""
    rp = active_runs.get(tool_id)
    if not rp:
        return []
    return list(rp.log_buffer)


def start_tool_with_ids(tool: dict, meeting_ids: list[str]) -> tuple[bool, str]:
    """Startet die CLI sequenziell für mehrere Meeting-IDs in einem Thread."""
    tool_id = tool["id"]

    if tool_id in active_runs:
        rp = active_runs[tool_id]
        if rp.status in ("running", "starting"):
            stop_tool(tool_id)
        del active_runs[tool_id]

    python_exe = get_python_exe(Path(tool["path"]))

    # Platzhalter-RunningProcess ohne echten Prozess
    rp = RunningProcess(
        tool_id=tool_id,
        pid=0,
        process=None,  # type: ignore
        status="starting",
    )
    rp.log_buffer.append(f"[Starte Download für {len(meeting_ids)} Meeting(s)]")
    active_runs[tool_id] = rp

    def _run_all():
        for i, mid in enumerate(meeting_ids, start=1):
            rp.log_buffer.append(f"\n--- Meeting {i}/{len(meeting_ids)}: {mid} ---")
            rp.status = "running"
            try:
                proc = subprocess.Popen(
                    [python_exe, "main.py", mid],
                    stdout=subprocess.PIPE,
                    stderr=STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=tool["path"],
                    env=os.environ.copy(),
                )
                rp.process = proc
                rp.pid = proc.pid
                for raw_line in proc.stdout:
                    rp.log_buffer.append(raw_line.rstrip("\n\r"))
                proc.wait()
                if proc.returncode != 0:
                    rp.log_buffer.append(f"[Fehler: Exit-Code {proc.returncode}]")
            except Exception as e:
                rp.log_buffer.append(f"[Fehler bei {mid}: {e}]")

        rp.status = "stopped"
        rp.log_buffer.append("\n[Alle Downloads abgeschlossen]")

    threading.Thread(target=_run_all, daemon=True).start()
    return True, ""


def start_tool_delete_ids(tool: dict, meeting_ids: list[str]) -> tuple[bool, str]:
    """Löscht Fireflies-Aufnahmen sequenziell per CLI."""
    tool_id = tool["id"] + "__delete"  # separater Slot, stört nicht den Download-Slot

    if tool_id in active_runs:
        rp = active_runs[tool_id]
        if rp.status in ("running", "starting"):
            stop_tool(tool_id)
        del active_runs[tool_id]

    python_exe = get_python_exe(Path(tool["path"]))

    rp = RunningProcess(
        tool_id=tool_id,
        pid=0,
        process=None,  # type: ignore
        status="starting",
    )
    rp.log_buffer.append(f"[Lösche {len(meeting_ids)} Aufnahme(n) von Fireflies]")
    active_runs[tool_id] = rp

    def _delete_all():
        for i, mid in enumerate(meeting_ids, start=1):
            rp.log_buffer.append(f"\n--- Lösche {i}/{len(meeting_ids)}: {mid} ---")
            rp.status = "running"
            try:
                proc = subprocess.Popen(
                    [python_exe, "main.py", "--delete", mid],
                    stdout=subprocess.PIPE,
                    stderr=STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    cwd=tool["path"], env=os.environ.copy(),
                )
                rp.process = proc
                rp.pid = proc.pid
                for raw_line in proc.stdout:
                    rp.log_buffer.append(raw_line.rstrip("\n\r"))
                proc.wait()
                if proc.returncode != 0:
                    rp.log_buffer.append(f"[Fehler: Exit-Code {proc.returncode}]")
            except Exception as e:
                rp.log_buffer.append(f"[Fehler bei {mid}: {e}]")

        rp.status = "stopped"
        rp.log_buffer.append("\n[Alle Löschvorgänge abgeschlossen]")

    threading.Thread(target=_delete_all, daemon=True).start()
    return True, ""
