@echo off
cd /d "%~dp0"
echo.
echo Starte abp Toolboard...
echo Oeffne http://127.0.0.1:8080 im Browser
echo.

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
)

python app.py
pause
