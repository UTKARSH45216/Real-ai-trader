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
from groq_brain import GroqBrain
from openrouter_brain import OpenRouterBrain
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
    'last_decision': {},
    'last_trade': {},
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
        if self.broker == "alpaca":
            return self._is_us_market_open()
        elif self.broker == "zerodha":
            return self._is_india_market_open()
        return False
        
    def _is_us_market_open(self) -> bool:
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        if now.weekday() >= 5:
            return False
        return time(9, 30) <= now.time() < time(16, 0)
        
    def _is_india_market_open(self) -> bool:
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        if now.weekday() >= 5:
            return False
        return time(9, 15) <= now.time() < time(15, 30)
        
    def get_next_opening_time(self) -> str:
        if self.broker == "alpaca":
            return self._get_us_next_opening()
        return "Unknown"
        
    def _get_us_next_opening(self) -> str:
        et = pytz.timezone('US/Eastern')
        now = datetime.now(et)
        while now.weekday() >= 5:
            now = datetime.fromtimestamp(now.timestamp() + 86400, tz=et)
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if now.time() < time(9, 30):
            return market_open.strftime("%Y-%m-%d %H:%M:%S %Z")
        next_day = datetime.fromtimestamp(now.timestamp() + 86400, tz=et)
        while next_day.weekday() >= 5:
            next_day = datetime.fromtimestamp(next_day.timestamp() + 86400, tz=et)
        return next_day.replace(hour=9, minute=30, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S %Z")
class TradingBotService:
    """Trading bot running as a service with embedded risk metrics."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.AI_PROVIDER == "groq":
            self.ai_brain = GroqBrain(settings)
        else:
            self.ai_brain = OpenRouterBrain(settings)
        self.market_checker = MarketHoursChecker(settings.BROKER)
        self.executor = AlpacaExecutor(settings) if settings.BROKER == "alpaca" else ZerodhaExecutor(settings)
        self.is_running = False
        
    async def initialize(self) -> bool:
        try:
            logger.info("Initializing Trading Bot Service...")
            account = await self.executor.get_account()
            bot_state['account_info'] = account
            model_info = self.ai_brain.get_model_info()
            positions = await self.executor.get_positions()
            bot_state['positions'] = positions
            bot_state['status'] = 'WAITING_FOR_MARKET'
            return True
        except Exception as e:
            logger.error(f"Initialization failed: {str(e)}")
            bot_state['status'] = 'ERROR'
            return False
            
    async def run_trading_cycle(self) -> None:
        bot_state['iterations'] += 1
        cycle_start = datetime.now()
        
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"CYCLE #{bot_state['iterations']} | {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*60}")
            
            # Stop-loss tracking
            current_positions = await self.executor.get_positions()
            STOP_LOSS_PERC = -0.02 
            
            for pos in current_positions:
                symbol = pos['symbol']
                unrealized_plpc = pos.get('unrealized_plpc', 0.0)
                
                if unrealized_plpc <= STOP_LOSS_PERC:
                    logger.warning(f"🚨 AUTOMATED RISK SAFETY TRIGGERED: [{symbol}] down {unrealized_plpc*100:.2f}%. Liquidating!")
                    await self.executor.execute_trade(
                        symbol=symbol,
                        decision='SELL',
                        quantity=int(pos['qty']),
                        reason="Emergency risk boundary breached"
                    )
                    continue

            market_data = await self.executor.fetch_market_data()
            if not market_data:
                logger.warning("No market data available, skipping cycle")
                return
                
            for symbol, single_asset_data in market_data.items():
                packaged_data = {symbol: single_asset_data}
                decision = self.ai_brain.analyze_patterns(packaged_data)
                
                with bot_lock:
                    bot_state['last_decision'][symbol] = decision
                
                if decision['decision'] in ['BUY', 'SELL']:
                    execution_result = await self.executor.execute_trade(
                        symbol=symbol,
                        decision=decision['decision'],
                        quantity=decision.get('quantity', 1),
                        reason=decision['reason']
                    )
                    if execution_result:
                        with bot_lock:
                            bot_state['last_trade'][symbol] = execution_result
                else:
                    logger.info(f"[{symbol}] Status: HOLD")
                    
            updated_positions = await self.executor.get_positions()
            account = await self.executor.get_account()
            
            with bot_lock:
                bot_state['positions'] = updated_positions
                bot_state['account_info'] = account
                
            bot_state['last_cycle_time'] = (datetime.now() - cycle_start).total_seconds()
            
        except Exception as e:
            logger.error(f"Error in trading cycle: {str(e)}")

    async def run(self) -> None:
        self.is_running = True
        if not await self.initialize():
            return
            
        while self.is_running:
            if self.market_checker.is_market_open():
                bot_state['market_open'] = True
                bot_state['status'] = 'MARKET_OPEN - TRADING'
                await self.run_trading_cycle()
                await asyncio.sleep(max(10, self.settings.CYCLE_INTERVAL_SECONDS))
            else:
                bot_state['market_open'] = False
                bot_state['status'] = 'MARKET_CLOSED - WAITING'
                await asyncio.sleep(30)
bot_service = None
bot_thread = None

def run_bot_async():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        bot = TradingBotService(settings)
        loop.run_until_complete(bot.run())
    except Exception as e:
        logger.error(f"Bot thread crashed: {str(e)}")
    finally:
        loop.close()

def start_bot():
    global bot_thread
    if bot_thread is None or not bot_thread.is_alive():
        bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        bot_thread.start()
        logger.info("Bot thread started")

start_bot()

# ============ Flask Routes ============
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/status', methods=['GET'])
def status():
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
            'error': bot_state['error']
        }), 200

@app.route('/positions', methods=['GET'])
def positions():
    with bot_lock:
        return jsonify({'positions': bot_state['positions'], 'count': len(bot_state['positions'])}), 200

@app.route('/account', methods=['GET'])
def account():
    with bot_lock:
        return jsonify({'account': bot_state['account_info']}), 200

@app.route('/logs/latest', methods=['GET'])
def latest_logs():
    try:
        with open('trading_bot.log', 'r') as f:
            logs = f.readlines()[-50:]
        return jsonify({'logs': logs, 'count': len(logs)}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/start', methods=['POST'])
def start():
    try:
        start_bot()
        return jsonify({'message': 'Bot started', 'status': bot_state['status']}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/', methods=['GET'])
def index():
    return jsonify({'name': 'Automated Trading Bot API', 'version': '3.0-DynamicSizing'}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
