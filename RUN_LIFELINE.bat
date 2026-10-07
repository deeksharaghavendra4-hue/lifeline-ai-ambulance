@echo off
title LifeLine Ambulance AI
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    py -3 -m venv venv
    if errorlevel 1 (
        echo Failed to create the Python environment.
        echo Make sure Python is installed and available through the py launcher.
        pause
        exit /b 1
    )
)

echo Installing required packages...
venv\Scripts\python.exe -m pip install -r backend\requirements.txt

echo.
echo Make sure PostgreSQL is installed and DATABASE_URL is configured in .env.
echo Starting LifeLine Ambulance AI...
echo Open http://localhost:5000
echo.
venv\Scripts\python.exe run.py
pause
