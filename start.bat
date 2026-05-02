@echo off
cd /d "%~dp0"
echo.
echo  abp Toolboard wird gestartet...
echo.

REM venv erstellen falls nicht vorhanden
if not exist ".venv\Scripts\activate.bat" (
    echo  Erstelle virtuelle Umgebung...
    python -m venv .venv
    if errorlevel 1 (
        echo FEHLER: Python venv konnte nicht erstellt werden.
        pause
        exit /b 1
    )
)

REM venv aktivieren
call .venv\Scripts\activate.bat

REM Flask pruefen, ggf. installieren
python -c "import flask" 2>nul
if errorlevel 1 (
    echo  Installiere Abhaengigkeiten (einmalig)...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo FEHLER: Installation fehlgeschlagen.
        pause
        exit /b 1
    )
)

echo  Server laeuft auf http://127.0.0.1:8080
echo  Browser wird automatisch geoeffnet...
echo  Fenster schliessen beendet den Server.
echo.

python app.py
pause
