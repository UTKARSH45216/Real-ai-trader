"""
Alpaca trading executor using alpaca-py.
Handles market data fetching and order execution.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from config import Settings

logger = logging.getLogger(__name__)


class AlpacaExecutor:
    """Handles Alpaca API interactions and order execution."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = TradingClient(
            api_key=settings.ALPACA_API_KEY,
            secret_key=settings.ALPACA_SECRET_KEY,
            base_url=settings.ALPACA_BASE_URL
        )
    
    async def get_account(self) -> Dict[str, Any]:
        """Fetch account information."""
        try:
            account = self.client.get_account()
            return {
                'id': account.id,
                'cash': float(account.cash),
                'buying_power': float(account.buying_power),
                'portfolio_value': float(account.portfolio_value),
                'multiplier': float(account.multiplier),
                'status': account.account_status
            }
        except Exception as e:
            logger.error(f"Error fetching account: {str(e)}")
            return {}
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch current open positions."""
        try:
            positions_response = self.client.get_all_positions()
            positions = []
            
            for pos in positions_response:
                positions.append({
                    'symbol': pos.symbol,
                    'qty': float(pos.qty),
                    'avg_fill_price': float(pos.avg_fill_price),
                    'current_price': float(pos.current_price),
                    'unrealized_pl': float(pos.unrealized_pl),
                    'unrealized_plpc': float(pos.unrealized_plpc),
                    'side': pos.side
                })
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            return []
    
    async def fetch_market_data(self) -> Dict[str, Dict[str, Any]]:
        """Fetch live 1-minute OHLCV data for monitored symbols."""
        market_data = {}
        
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            
            client = StockHistoricalDataClient(
                api_key=self.settings.ALPACA_API_KEY,
                secret_key=self.settings.ALPACA_SECRET_KEY
            )
            
            # Fetch latest bar data
            request_params = StockBarsRequest(
                symbol_or_symbols=self.settings.SYMBOLS_TO_MONITOR,
                timeframe=TimeFrame.Minute,
                limit=20
            )
            
            bars = client.get_stock_bars(request_params)
            
            for symbol in self.settings.SYMBOLS_TO_MONITOR:
                try:
                    if symbol not in bars.data:
                        logger.warning(f"No data for {symbol}")
                        continue
                    
                    bar_list = bars.data[symbol]
                    if not bar_list:
                        continue
                    
                    latest_bar = bar_list[-1]
                    
                    # Calculate technical indicators
                    rsi = self._calculate_rsi(symbol, bar_list)
                    ma20 = self._calculate_moving_average(symbol, bar_list, 20)
                    change_pct = ((latest_bar.close - latest_bar.open) / latest_bar.open * 100) if latest_bar.open > 0 else 0
                    
                    market_data[symbol] = {
                        'ohlcv': {
                            'open': float(latest_bar.open),
                            'high': float(latest_bar.high),
                            'low': float(latest_bar.low),
                            'close': float(latest_bar.close),
                            'volume': int(latest_bar.volume)
                        },
                        'rsi': rsi,
                        'ma20': ma20,
                        'change_pct': round(change_pct, 2),
                        'timestamp': latest_bar.timestamp
                    }
                    
                except Exception as e:
                    logger.warning(f"Error processing data for {symbol}: {str(e)}")
                    continue
            
            return market_data
            
        except Exception as e:
            logger.error(f"Error fetching market data: {str(e)}")
            return {}
    
    def _calculate_rsi(self, symbol: str, bars: list, period: int = 14) -> Optional[float]:
        """Calculate RSI for a symbol."""
        try:
            if len(bars) < period + 1:
                return None
            
            closes = [float(b.close) for b in bars[-period-1:]]
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            
            gains = sum(d for d in deltas if d > 0) / period
            losses = abs(sum(d for d in deltas if d < 0)) / period
            
            if losses == 0:
                return 100.0
            
            rs = gains / losses
            rsi = 100 - (100 / (1 + rs))
            
            return round(rsi, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating RSI for {symbol}: {str(e)}")
            return None
    
    def _calculate_moving_average(self, symbol: str, bars: list, period: int) -> Optional[float]:
        """Calculate moving average for a symbol."""
        try:
            if len(bars) < period:
                return None
            
            closes = [float(b.close) for b in bars[-period:]]
            ma = sum(closes) / len(closes)
            
            return round(ma, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating MA for {symbol}: {str(e)}")
            return None
    
    async def execute_trade(self, decision: str, reason: str) -> Optional[Dict[str, Any]]:
        """Execute a buy or sell order."""
        try:
            if decision not in ['BUY', 'SELL']:
                logger.warning(f"Invalid decision: {decision}")
                return None
            
            # Use first monitored symbol for simplicity (production: add symbol selection)
            symbol = self.settings.SYMBOLS_TO_MONITOR[0]
            
            # Verify we don't exceed max positions
            positions = await self.get_positions()
            if len(positions) >= self.settings.MAX_POSITIONS and decision == 'BUY':
                logger.warning(f"Max positions ({self.settings.MAX_POSITIONS}) reached, skipping BUY")
                return None
            
            # Check position exists for SELL
            position_exists = any(p['symbol'] == symbol for p in positions)
            if decision == 'SELL' and not position_exists:
                logger.warning(f"No position in {symbol}, skipping SELL")
                return None
            
            # Execute order
            order_request = MarketOrderRequest(
                symbol=symbol,
                qty=self.settings.ORDER_QUANTITY if decision == 'BUY' else -self.settings.ORDER_QUANTITY,
                side=OrderSide.BUY if decision == 'BUY' else OrderSide.SELL,
                time_in_force=TimeInForce.DAY
            )
            
            order = self.client.submit_order(order_request)
            
            logger.info(f"Order submitted: {symbol} {decision} x{self.settings.ORDER_QUANTITY}")
            logger.info(f"Reason: {reason}")
            
            return {
                'order_id': order.id,
                'symbol': order.symbol,
                'qty': float(order.qty),
                'side': order.side,
                'type': order.order_type,
                'status': order.status
            }
            
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}", exc_info=True)
            return None
