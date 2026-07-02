#!/usr/bin/env python3
"""
Main orchestrator for the automated trading bot.
Runs async loop every 60 seconds, fetching market data and executing trades.
"""

import asyncio
import logging
import sys
from datetime import datetime
from typing import Optional, Union

from config import Settings
from openrouter_brain import OpenRouterBrain
from groq_brain import GroqBrain
from alpaca_executor import AlpacaExecutor
from zerodha_executor import ZerodhaExecutor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """Main trading bot orchestrator."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.AI_PROVIDER == "groq":
            self.ai_brain = GroqBrain(settings)
        else:
            self.ai_brain = OpenRouterBrain(settings)
        
        # Initialize broker executor based on configuration
        if settings.BROKER == "alpaca":
            self.executor = AlpacaExecutor(settings)
            logger.info(f"Initialized Alpaca executor (US Markets)")
        elif settings.BROKER == "zerodha":
            self.executor = ZerodhaExecutor(settings)
            logger.info(f"Initialized Zerodha executor (Indian Markets)")
        else:
            raise ValueError(f"Unknown broker: {settings.BROKER}")
        
        self.is_running = False
        self.iterations = 0
        
    async def initialize(self) -> bool:
        """Initialize bot and verify connectivity."""
        try:
            logger.info("Initializing Trading Bot...")
            
            # Verify broker connection
            account = await self.executor.get_account()
            broker_name = self.settings.BROKER.upper()
            logger.info(f"✓ Connected to {broker_name} | Account: {account.get('id', 'unknown')}")
            logger.info(f"  Cash: ${account.get('cash', 0):.2f} | Buying Power: ${account.get('buying_power', 0):.2f}")
            
            # Verify AI brain connection
            model_info = self.ai_brain.get_model_info()
            logger.info(f"✓ Connected to {self.settings.AI_PROVIDER.upper()} | Model: {model_info}")
            
            # Get initial positions
            positions = await self.executor.get_positions()
            logger.info(f"✓ Current positions: {len(positions)} open trades")
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization failed: {str(e)}", exc_info=True)
            return False
    
    async def run_trading_cycle(self) -> None:
        """Execute a single trading cycle."""
        self.iterations += 1
        cycle_start = datetime.now()
        
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"CYCLE #{self.iterations} | {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"{'='*60}")
            
            # Step 1: Fetch market data
            market_data = await self.executor.fetch_market_data()
            if not market_data:
                logger.warning("No market data available, skipping cycle")
                return
            
            logger.info(f"Market data fetched: {len(market_data)} symbols")
            
            # Step 2: Get AI analysis
            decision = self.ai_brain.analyze_patterns(market_data)
            logger.info(f"AI Decision: {decision['decision']} | Reason: {decision['reason'][:100]}...")
            
            # Step 3: Execute orders if signal present
            if decision['decision'] in ['BUY', 'SELL']:
                execution_result = await self.executor.execute_trade(
                    decision=decision['decision'],
                    reason=decision['reason']
                )
                
                if execution_result:
                    logger.info(f"✓ Trade executed: {execution_result}")
                else:
                    logger.warning("Trade execution returned no result")
            else:
                logger.info("Holding position - no action taken")
            
            # Step 4: Log portfolio status
            positions = await self.executor.get_positions()
            logger.info(f"Portfolio: {len(positions)} active positions")
            
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            logger.info(f"Cycle completed in {cycle_duration:.2f}s")
            
        except asyncio.CancelledError:
            logger.info("Trading cycle cancelled")
            raise
            
        except Exception as e:
            logger.error(f"Error in trading cycle: {str(e)}", exc_info=True)
            # Continue running despite errors (resilience)
    
    async def run(self) -> None:
        """Main bot loop - runs every 60 seconds."""
        self.is_running = True
        logger.info("Starting Trading Bot Main Loop...")
        
        if not await self.initialize():
            logger.error("Failed to initialize bot. Exiting.")
            return
        
        try:
            while self.is_running:
                try:
                    await self.run_trading_cycle()
                    
                    # Wait 60 seconds before next cycle
                    logger.info(f"Waiting {self.settings.CYCLE_INTERVAL_SECONDS}s until next cycle...")
                    await asyncio.sleep(self.settings.CYCLE_INTERVAL_SECONDS)
                    
                except asyncio.CancelledError:
                    logger.info("Bot loop cancelled")
                    break
                    
        except KeyboardInterrupt:
            logger.info("Bot interrupted by user")
            
        finally:
            self.is_running = False
            logger.info("Trading Bot stopped")
    
    async def shutdown(self) -> None:
        """Graceful shutdown."""
        self.is_running = False
        logger.info("Shutting down Trading Bot...")


async def main():
    """Entry point."""
    try:
        settings = Settings()
        bot = TradingBot(settings)
        
        await bot.run()
        
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
