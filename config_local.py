"""
config_local.py - Local development configuration with API keys
DO NOT COMMIT THIS FILE - It's in .gitignore

Copy this file to config_local.py and add your actual API keys here.
The config.py will automatically load these values for local development.
"""

# Gemini API Configuration
GEMINI_API_KEY = "AQ.Ab8RN6KzlEIqusWIMCdxO1na96E99RfMZS7F-O-tFGFq3njU6w"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_TEMPERATURE = 0.1
GEMINI_MAX_TOKENS = 500

# Alpaca API Configuration (US Markets)
ALPACA_API_KEY = "PKCHN5RYOIRBOMRAXTJYFHHSSK"
ALPACA_SECRET_KEY = "AgAsAikvLfrTPWBvvYvwZXkNBkMDB2ZFSDna8BbQk82S"
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"

# Zerodha API Configuration (Indian Markets) - Optional
ZERODHA_API_KEY = "your_zerodha_api_key_here"
ZERODHA_ACCESS_TOKEN = "your_zerodha_access_token_here"

# Trading Configuration
BROKER = "alpaca"
CYCLE_INTERVAL_SECONDS = 60
SYMBOLS_TO_MONITOR = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA"]
ORDER_QUANTITY = 1
MAX_POSITIONS = 5

# Risk Management
STOP_LOSS_PERCENT = 0.02
TAKE_PROFIT_PERCENT = 0.05
MAX_DAILY_LOSS = 1000.0
