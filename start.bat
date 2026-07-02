@echo off
REM Trading Bot Startup Script for Windows

echo 🤖 Starting Automated Trading Bot...

REM Check if .env exists
if not exist .env (
    echo ❌ .env file not found!
    echo Please create .env file with your API keys
    exit /b 1
)

REM Check if venv exists
if not exist venv (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate venv
echo 🔌 Activating virtual environment...
call venv\Scripts\activate

REM Install requirements
echo 📥 Installing dependencies...
pip install -r requirements.txt -q

REM Start bot
echo ✅ Starting Flask web service...
echo 📍 Bot will be available at http://localhost:5000
echo.
echo API Endpoints:
echo   - Status: http://localhost:5000/status
echo   - Positions: http://localhost:5000/positions
echo   - Logs: http://localhost:5000/logs/latest
echo   - Health: http://localhost:5000/health
echo.
echo Press Ctrl+C to stop
echo.

python app.py

pause
