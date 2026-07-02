#!/bin/bash

# Trading Bot Startup Script

echo "🤖 Starting Automated Trading Bot..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please create .env file with your API keys"
    exit 1
fi

# Check if venv exists
if [ ! -d venv ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate venv
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "📥 Installing dependencies..."
pip install -r requirements.txt -q

# Start bot
echo "✅ Starting Flask web service..."
echo "📍 Bot will be available at http://localhost:5000"
echo ""
echo "API Endpoints:"
echo "  - Status: http://localhost:5000/status"
echo "  - Positions: http://localhost:5000/positions"
echo "  - Logs: http://localhost:5000/logs/latest"
echo "  - Health: http://localhost:5000/health"
echo ""
echo "Press Ctrl+C to stop"
echo ""

python app.py
