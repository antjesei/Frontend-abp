@echo off
cd /d "%~dp0"
echo.
echo  abp Toolboard wird gestartet...
echo.

REM venv erstellen falls nicht vorhanden
if not exist ".venv\Scripts\python.exe" (
    echo  Erstelle virtuelle Umgebung...
    python -m venv .venv
    if errorlevel 1 (
        echo FEHLER: Python venv konnte nicht erstellt werden.
        pause & exit /b 1
    )
)

REM Dependencies pruefen und ggf. installieren
".venv\Scripts\python.exe" -c "import flask" 2>nul
if errorlevel 1 (
    echo  Installiere Abhaengigkeiten - bitte warten...
    ".venv\Scripts\pip.exe" install -r requirements.txt
    if errorlevel 1 (
        echo FEHLER: Installation fehlgeschlagen.
        pause & exit /b 1
    )
    echo.
)

REM Alten Server beenden falls noch aktiv
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8080 "') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM Flask im Hintergrund starten
echo  Starte Server...
start /b "" ".venv\Scripts\python.exe" app.py

REM Warten bis Port 8080 antwortet (max. 30 Sekunden)
echo  Warte auf Server...
set ATTEMPTS=0
:WAIT
set /a ATTEMPTS+=1
if %ATTEMPTS% gtr 30 (
    echo.
    echo FEHLER: Server nicht erreichbar nach 30 Sekunden.
    echo Bitte server.log pruefen.
    pause & exit /b 1
)
powershell -NoProfile -Command ^
    "try { $c=New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1',8080); $c.Close(); exit 0 } catch { exit 1 }" ^
    2>nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto WAIT
)

REM Browser oeffnen
echo  Oeffne Browser...
start "" "http://127.0.0.1:8080"
echo.
echo  Server laeuft auf http://127.0.0.1:8080
echo  Dieses Fenster offen lassen - Schliessen beendet den Server.
echo.
pause
