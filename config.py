"""
Configuration module for Trading Bot
Uses environment variables without pydantic
"""

import os
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings:
    """App settings loaded from environment variables"""
    
    def __init__(self):
        # Broker settings
        self.BROKER = os.getenv("BROKER", "alpaca")
        
        # API Keys
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
        self.GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))
        
        # Alpaca settings
        self.ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "")
        self.ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
        self.ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        
        # Zerodha settings
        self.ZERODHA_API_KEY = os.getenv("ZERODHA_API_KEY", "")
        self.ZERODHA_ACCESS_TOKEN = os.getenv("ZERODHA_ACCESS_TOKEN", "")
        self.ZERODHA_REDIRECT_URL = os.getenv("ZERODHA_REDIRECT_URL", "http://localhost:8080")
        
        # Trading settings
        symbols_str = os.getenv("SYMBOLS_TO_MONITOR", '["AAPL","MSFT"]')
        try:
            self.SYMBOLS_TO_MONITOR = json.loads(symbols_str)
        except:
            self.SYMBOLS_TO_MONITOR = ["AAPL", "MSFT"]
        
        self.ORDER_QUANTITY = int(os.getenv("ORDER_QUANTITY", "1"))
        self.MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "5"))
        self.CYCLE_INTERVAL_SECONDS = int(os.getenv("CYCLE_INTERVAL_SECONDS", "60"))
        
        # Server settings
        self.PORT = int(os.getenv("PORT", "5000"))
        self.DEBUG = os.getenv("DEBUG", "False").lower() == "true"
        
    def validate(self):
        """Validate that required settings are present"""
        errors = []
        
        if not self.GEMINI_API_KEY:
            errors.append("GEMINI_API_KEY is required")
        
        if self.BROKER == "alpaca":
            if not self.ALPACA_API_KEY:
                errors.append("ALPACA_API_KEY is required for broker=alpaca")
            if not self.ALPACA_SECRET_KEY:
                errors.append("ALPACA_SECRET_KEY is required for broker=alpaca")
        
        elif self.BROKER == "zerodha":
            if not self.ZERODHA_API_KEY:
                errors.append("ZERODHA_API_KEY is required for broker=zerodha")
            if not self.ZERODHA_ACCESS_TOKEN:
                errors.append("ZERODHA_ACCESS_TOKEN is required for broker=zerodha")
        
        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(errors))
    
    def __repr__(self):
        return f"Settings(broker={self.BROKER}, symbols={self.SYMBOLS_TO_MONITOR}, port={self.PORT})"


# Create default settings instance
settings = Settings()

