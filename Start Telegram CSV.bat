@echo off
cd /d "%~dp0"
if exist "telegram-csv-ui.exe" (
    "telegram-csv-ui.exe" %*
) else if exist ".ui-venv\Scripts\python.exe" (
    ".ui-venv\Scripts\python.exe" launch.py %*
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" launch.py %*
) else (
    where py >nul 2>nul
    if errorlevel 1 (
        python launch.py %*
    ) else (
        py -3 launch.py %*
    )
)
if errorlevel 1 (
    echo Launch failed. Source installs need Python 3.10 or newer.
    pause
)
