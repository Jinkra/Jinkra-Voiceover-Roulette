@echo off
cd /d "%~dp0"
if exist "Jinkra Voiceover Roulette.exe" (
    start "" "Jinkra Voiceover Roulette.exe"
    exit /b
)
if exist "dist\Jinkra\Jinkra Voiceover Roulette.exe" (
    start "" "dist\Jinkra\Jinkra Voiceover Roulette.exe"
    exit /b
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" sr_roulette.py
) else (
    py -3 sr_roulette.py
)
if errorlevel 1 pause
