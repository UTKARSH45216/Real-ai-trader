"""
Flask web service for the trading bot.
Runs as 24/7 service on Render with intelligent market hour detection.
"""

import asyncio
import logging
import threading
import os
from datetime import datetime, time
import pytz
from typing import Dict, Any

from flask import Flask, jsonify
from config import Settings
from gemini_brain import GeminiBrain
from alpaca_executor import AlpacaExecutor
from zerodha_executor import ZerodhaExecutor

app = Flask(__name__)
settings = Settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global bot state
bot_state = {
    'status': 'STARTING',
    'market_open': False,
    'current_broker': settings.BROKER,
    'iterations': 0,
    'last_cycle_time': None,
    'last_decision': None,
    'last_trade': None,
    'account_info': {},
    'positions': [],
    'error': None
}

bot_lock = threading.Lock()


class MarketHoursChecker:
    """Check if market is open based on broker and timezone."""
    
    def __init__(self, broker: str):
        self.broker = broker
    
    def is_market_open(self) -> bool:
        """Check if market is currently open."""
        if self.broker == "alpaca":
            return self._is_us_market_open()
        elif self.broker == "zerodha":
            return self._is_india_market_open()
        return False
    
    def _is_us_market_open(self) -> bool:
        """US market: 9:30 AM - 4:00 PM ET, Monday-Friday."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        
        # Check if it's a weekday
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Check market hours: 9:30 AM - 4:00 PM ET
        market_open = time(9, 30)
        market_close = time(16, 0)
        
        return market_open <= now.time() < market_close
    
    def _is_india_market_open(self) -> bool:
        """India market: 9:15 AM - 3:30 PM IST, Monday-Friday."""
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        # Check if it's a weekday
        if now.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Check market hours: 9:15 AM - 3:30 PM IST
        market_open = time(9, 15)
        market_close = time(15, 30)
        
        return market_open <= now.time() < market_close
    
    def get_next_opening_time(self) -> str:
        """Get time until next market opening."""
        if self.broker == "alpaca":
            return self._get_us_next_opening()
        elif self.broker == "zerodha":
            return self._get_india_next_opening()
        return "Unknown"
    
    def _get_us_next_opening(self) -> str:
        """Get next US market opening time."""
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        
        # If today is not a market day, get next Monday
        while now.weekday() >= 5:
            now = datetime.fromtimestamp(
                now.timestamp() + 86400,
                tz=et
            )
        
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        
        if now.time() < time(9, 30):
            return market_open.strftime("%Y-%m-%d %H:%M:%S %Z")
        
        # Next day
        next_day = datetime.fromtimestamp(
            now.timestamp() + 86400,
            tz=et
        )
        while next_day.weekday() >= 5:
            next_day = datetime.fromtimestamp(
                next_day.timestamp() + 86400,
                tz=et
            )
        
        return next_day.replace(hour=9, minute=30, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S %Z")
    
    def _get_india_next_opening(self) -> str:
        """Get next India market opening time."""
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        # If today is not a market day, get next Monday
        while now.weekday() >= 5:
            now = datetime.fromtimestamp(
                now.timestamp() + 86400,
                tz=ist
            )
        
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        
        if now.time() < time(9, 15):
            return market_open.strftime("%Y-%m-%d %H:%M:%S %Z")
        
        # Next day
        next_day = datetime.fromtimestamp(
            now.timestamp() + 86400,
            tz=ist
        )
        while next_day.weekday() >= 5:
            next_day = datetime.fromtimestamp(
                next_day.timestamp() + 86400,
                tz=ist
            )
        
        return next_day.replace(hour=9, minute=15, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S %Z")


class TradingBotService:
    """Trading bot that runs as a service."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gemini_brain = GeminiBrain(settings)
        self.market_checker = MarketHoursChecker(settings.BROKER)
        
        # Initialize broker executor
        if settings.BROKER == "alpaca":
            self.executor = AlpacaExecutor(settings)
        elif settings.BROKER == "zerodha":
            self.executor = ZerodhaExecutor(settings)
        else:
            raise ValueError(f"Unknown broker: {settings.BROKER}")
        
        self.is_running = False
    
    async def initialize(self) -> bool:
        """Initialize bot and verify connectivity."""
        try:
            logger.info("Initializing Trading Bot Service...")
            
            # Verify broker connection
            account = await self.executor.get_account()
            bot_state['account_info'] = account
            
            logger.info(f"✓ Connected to {self.settings.BROKER.upper()} | Account: {account.get('id', 'unknown')}")
            logger.info(f"  Cash: ${account.get('cash', 0):.2f} | Buying Power: ${account.get('buying_power', 0):.2f}")
            
            # Verify Gemini connection
            model_info = self.gemini_brain.get_model_info()
            logger.info(f"✓ Connected to Gemini | Model: {model_info}")
            
            # Get initial positions
            positions = await self.executor.get_positions()
            bot_state['positions'] = positions
            logger.info(f"✓ Current positions: {len(positions)} open trades")
            
            bot_state['status'] = 'WAITING_FOR_MARKET'
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {str(e)}", exc_info=True)
            bot_state['error'] = str(e)
            bot_state['status'] = 'ERROR'
            return False
    
    async def run_trading_cycle(self) -> None:
        """Execute a single trading cycle."""
        bot_state['iterations'] += 1
        cycle_start = datetime.now()
        
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"CYCLE #{bot_state['iterations']} | {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*60}")
            
            # Step 1: Fetch market data
            market_data = await self.executor.fetch_market_data()
            if not market_data:
                logger.warning("No market data available, skipping cycle")
                return
            
            logger.info(f"Market data fetched: {len(market_data)} symbols")
            
            # Step 2: Get Gemini analysis
            decision = self.gemini_brain.analyze_patterns(market_data)
            bot_state['last_decision'] = decision
            logger.info(f"Gemini Decision: {decision['decision']} | Reason: {decision['reason'][:100]}...")
            
            # Step 3: Execute orders if signal present
            if decision['decision'] in ['BUY', 'SELL']:
                execution_result = await self.executor.execute_trade(
                    decision=decision['decision'],
                    reason=decision['reason']
                )
                
                if execution_result:
                    bot_state['last_trade'] = execution_result
                    logger.info(f"✓ Trade executed: {execution_result}")
                else:
                    logger.warning("Trade execution returned no result")
            else:
                logger.info("Holding position - no action taken")
            
            # Step 4: Update portfolio status
            positions = await self.executor.get_positions()
            account = await self.executor.get_account()
            bot_state['positions'] = positions
            bot_state['account_info'] = account
            logger.info(f"Portfolio: {len(positions)} active positions")
            
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            bot_state['last_cycle_time'] = cycle_duration
            logger.info(f"Cycle completed in {cycle_duration:.2f}s")
            
        except Exception as e:
            logger.error(f"Error in trading cycle: {str(e)}", exc_info=True)
            bot_state['error'] = str(e)
    
    async def run(self) -> None:
        """Main bot loop - runs 24/7."""
        self.is_running = True
        logger.info("Starting Trading Bot Service (24/7)...")
        
        if not await self.initialize():
            logger.error("Failed to initialize bot.")
            return
        
        try:
            while self.is_running:
                # Check market status every 10 seconds
                if self.market_checker.is_market_open():
                    bot_state['market_open'] = True
                    bot_state['status'] = 'MARKET_OPEN - TRADING'
                    
                    # Run trading cycle every 1 second when market is open
                    await self.run_trading_cycle()
                    await asyncio.sleep(1)
                
                else:
                    bot_state['market_open'] = False
                    bot_state['status'] = 'MARKET_CLOSED - WAITING'
                    next_opening = self.market_checker.get_next_opening_time()
                    logger.info(f"Market closed. Next opening: {next_opening}")
                    
                    # Check market status every 10 seconds
                    await asyncio.sleep(10)
        
        except Exception as e:
            logger.error(f"Fatal error in bot loop: {str(e)}", exc_info=True)
            bot_state['error'] = str(e)
            bot_state['status'] = 'ERROR'
        
        finally:
            self.is_running = False
            logger.info("Trading Bot Service stopped")


# Global bot instance
bot_service = None
bot_thread = None


def run_bot_async():
    """Run bot in asyncio event loop."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        bot = TradingBotService(settings)
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        logger.info("Bot interrupted")
    except Exception as e:
        # Catch anything that happens during bot construction or run(),
        # not just inside bot.run(), so startup errors are never silently
        # swallowed by the background thread.
        logger.error(f"Bot thread crashed: {str(e)}", exc_info=True)
        bot_state['status'] = 'ERROR'
        bot_state['error'] = str(e)
    finally:
        loop.close()


def start_bot():
    """Start bot in background thread."""
    global bot_thread
    
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        bot_thread.start()
        logger.info("Bot thread started")


# Start the bot as soon as this module is imported. This ensures it runs
# whether the app is launched directly (`python app.py`) or via a WSGI
# server like gunicorn (`gunicorn app:app`), since gunicorn never executes
# the `if __name__ == '__main__':` block below.
start_bot()


# ============ Flask Routes ============

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Render."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/status', methods=['GET'])
def status():
    """Get current bot status."""
    with bot_lock:
        return jsonify({
            'bot_status': bot_state['status'],
            'market_open': bot_state['market_open'],
            'broker': bot_state['current_broker'],
            'iterations': bot_state['iterations'],
            'last_cycle_time': bot_state['last_cycle_time'],
            'last_decision': bot_state['last_decision'],
            'last_trade': bot_state['last_trade'],
            'account': bot_state['account_info'],
            'positions_count': len(bot_state['positions']),
            'error': bot_state['error'],
            'timestamp': datetime.now().isoformat()
        }), 200


@app.route('/positions', methods=['GET'])
def positions():
    """Get current positions."""
    with bot_lock:
        return jsonify({
            'positions': bot_state['positions'],
            'count': len(bot_state['positions']),
            'timestamp': datetime.now().isoformat()
        }), 200


@app.route('/account', methods=['GET'])
def account():
    """Get account information."""
    with bot_lock:
        return jsonify({
            'account': bot_state['account_info'],
            'timestamp': datetime.now().isoformat()
        }), 200


@app.route('/logs/latest', methods=['GET'])
def latest_logs():
    """Get latest bot logs (last 50 lines)."""
    try:
        with open('trading_bot.log', 'r') as f:
            logs = f.readlines()[-50:]
        
        return jsonify({
            'logs': logs,
            'count': len(logs),
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/start', methods=['POST'])
def start():
    """Start the bot."""
    try:
        start_bot()
        return jsonify({
            'message': 'Bot started',
            'status': bot_state['status'],
            'timestamp': datetime.now().isoformat()
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/config', methods=['GET'])
def config():
    """Get bot configuration."""
    return jsonify({
        'broker': settings.BROKER,
        'symbols': settings.SYMBOLS_TO_MONITOR,
        'order_quantity': settings.ORDER_QUANTITY,
        'max_positions': settings.MAX_POSITIONS,
        'cycle_interval_when_closed': '10 seconds',
        'cycle_interval_when_open': '1 second',
        'timestamp': datetime.now().isoformat()
    }), 200


@app.route('/', methods=['GET'])
def index():
    """Landing page with API documentation."""
    return jsonify({
        'name': 'Automated Trading Bot API',
        'version': '2.0',
        'broker': settings.BROKER.upper(),
        'endpoints': {
            '/health': 'Health check',
            '/status': 'Get bot status',
            '/positions': 'Get current positions',
            '/account': 'Get account info',
            '/config': 'Get configuration',
            '/logs/latest': 'Get latest 50 log lines',
            '/start': 'Start the bot (POST)',
        },
        'market_hours': {
            'alpaca': '9:30 AM - 4:00 PM ET (Monday-Friday)',
            'zerodha': '9:15 AM - 3:30 PM IST (Monday-Friday)'
        },
        'status': bot_state['status'],
        'timestamp': datetime.now().isoformat()
    }), 200


if __name__ == '__main__':
    # Bot thread is already started at module import time (see start_bot()
    # call above), so it works the same way whether run via `python app.py`
    # or via gunicorn.
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
