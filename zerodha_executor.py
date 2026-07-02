"""
Zerodha Kite Connect executor for Indian market (NSE/BSE).
Handles market data fetching and order execution for Indian stocks.
"""

import logging
from typing import Dict, List, Optional, Any
from kiteconnect import KiteConnect

from config import Settings

logger = logging.getLogger(__name__)


class ZerodhaExecutor:
    """Handles Zerodha Kite Connect API interactions for Indian markets."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.kite = KiteConnect(
            api_key=settings.ZERODHA_API_KEY,
            access_token=settings.ZERODHA_ACCESS_TOKEN
        )
        self.instruments = {}
        self._load_instruments()
    
    def _load_instruments(self):
        """Load instrument tokens for monitoring symbols."""
        try:
            instruments = self.kite.instruments()
            # Map symbol to instrument token for NSE stocks
            for inst in instruments:
                if inst['exchange'] == 'NSE' and inst['segment'] == 'EQUITY':
                    symbol = inst['tradingsymbol']
                    if symbol in self.settings.SYMBOLS_TO_MONITOR:
                        self.instruments[symbol] = inst['instrument_token']
            
            logger.info(f"Loaded {len(self.instruments)} instruments from NSE")
            
        except Exception as e:
            logger.error(f"Error loading instruments: {str(e)}")
    
    async def get_account(self) -> Dict[str, Any]:
        """Fetch account information from Zerodha."""
        try:
            profile = self.kite.profile()
            margins = self.kite.margins()
            
            return {
                'id': profile.get('user_id', 'unknown'),
                'cash': float(margins['equity']['available']),
                'buying_power': float(margins['equity']['available']),
                'portfolio_value': float(margins['equity']['net']),
                'multiplier': 1.0,
                'status': 'ACTIVE'
            }
            
        except Exception as e:
            logger.error(f"Error fetching account: {str(e)}")
            return {}
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Fetch current open positions from Zerodha."""
        try:
            positions_response = self.kite.positions()
            positions = []
            
            # Day positions (intraday trades)
            for pos in positions_response.get('day', []):
                positions.append({
                    'symbol': pos['tradingsymbol'],
                    'qty': float(pos['quantity']),
                    'avg_fill_price': float(pos['average_price']),
                    'current_price': float(pos['last_price']),
                    'unrealized_pl': float(pos['pnl']),
                    'unrealized_plpc': (float(pos['pnl']) / (float(pos['average_price']) * float(pos['quantity'])) * 100) if float(pos['average_price']) * float(pos['quantity']) > 0 else 0,
                    'side': 'BUY' if float(pos['quantity']) > 0 else 'SELL'
                })
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            return []
    
    async def fetch_market_data(self) -> Dict[str, Dict[str, Any]]:
        """Fetch live market data for monitored symbols from Zerodha."""
        market_data = {}
        
        try:
            # Get quotes for all monitored symbols
            instrument_tokens = [self.instruments[sym] for sym in self.settings.SYMBOLS_TO_MONITOR 
                                 if sym in self.instruments]
            
            if not instrument_tokens:
                logger.warning("No valid instruments found")
                return market_data
            
            quotes = self.kite.quote(instrument_tokens)
            
            for symbol in self.settings.SYMBOLS_TO_MONITOR:
                if symbol not in self.instruments:
                    logger.warning(f"No instrument token for {symbol}")
                    continue
                
                token = self.instruments[symbol]
                quote_key = f"NSE:{symbol}"
                
                if quote_key not in quotes:
                    logger.warning(f"No quote data for {symbol}")
                    continue
                
                quote = quotes[quote_key]['quote']
                
                # Calculate technical indicators
                rsi = self._calculate_rsi(symbol, token)
                ma20 = self._calculate_moving_average(symbol, token, 20)
                change_pct = ((quote['last_price'] - quote['open']) / quote['open'] * 100) if quote['open'] > 0 else 0
                
                market_data[symbol] = {
                    'ohlcv': {
                        'open': float(quote['open']),
                        'high': float(quote['high']),
                        'low': float(quote['low']),
                        'close': float(quote['last_price']),
                        'volume': int(quote['volume'])
                    },
                    'rsi': rsi,
                    'ma20': ma20,
                    'change_pct': round(change_pct, 2),
                    'timestamp': quote.get('timestamp', None)
                }
            
            return market_data
            
        except Exception as e:
            logger.error(f"Error fetching market data: {str(e)}")
            return {}
    
    def _calculate_rsi(self, symbol: str, token: int, period: int = 14) -> Optional[float]:
        """Calculate RSI for a symbol using 1-minute candles."""
        try:
            # Fetch 1-minute candles
            candles = self.kite.historical_data(
                instrument_token=token,
                from_date="2024-01-01",
                to_date="2024-01-02",
                interval="minute"
            )
            
            if len(candles) < period + 1:
                return None
            
            closes = [float(c['close']) for c in candles[-period-1:]]
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
    
    def _calculate_moving_average(self, symbol: str, token: int, period: int) -> Optional[float]:
        """Calculate moving average for a symbol using 1-minute candles."""
        try:
            candles = self.kite.historical_data(
                instrument_token=token,
                from_date="2024-01-01",
                to_date="2024-01-02",
                interval="minute"
            )
            
            if len(candles) < period:
                return None
            
            closes = [float(c['close']) for c in candles[-period:]]
            ma = sum(closes) / len(closes)
            
            return round(ma, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating MA for {symbol}: {str(e)}")
            return None
    
    async def execute_trade(self, decision: str, reason: str) -> Optional[Dict[str, Any]]:
        """Execute a buy or sell order on Zerodha."""
        try:
            if decision not in ['BUY', 'SELL']:
                logger.warning(f"Invalid decision: {decision}")
                return None
            
            # Use first monitored symbol
            symbol = self.settings.SYMBOLS_TO_MONITOR[0]
            
            if symbol not in self.instruments:
                logger.warning(f"No instrument token for {symbol}")
                return None
            
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
            
            # Place order on Zerodha
            order_id = self.kite.place_order(
                tradingsymbol=symbol,
                exchange='NSE',
                quantity=self.settings.ORDER_QUANTITY,
                price=0,
                product='MIS',  # Margin Intraday Square-off
                order_type='MARKET',
                side='BUY' if decision == 'BUY' else 'SELL',
                validity='DAY',
                disclosed_quantity=0,
                trigger_price=None,
                iceberg_legs=None,
                iceberg_quantity=None,
                tag=None
            )
            
            logger.info(f"Order placed: {symbol} {decision} x{self.settings.ORDER_QUANTITY}")
            logger.info(f"Order ID: {order_id}")
            logger.info(f"Reason: {reason}")
            
            # Fetch order details
            orders = self.kite.orders()
            order_details = next((o for o in orders if o['order_id'] == order_id), None)
            
            if order_details:
                return {
                    'order_id': order_id,
                    'symbol': order_details['tradingsymbol'],
                    'qty': float(order_details['quantity']),
                    'side': order_details['transaction_type'],
                    'type': order_details['order_type'],
                    'status': order_details['status']
                }
            
            return {
                'order_id': order_id,
                'symbol': symbol,
                'qty': self.settings.ORDER_QUANTITY,
                'side': decision,
                'type': 'MARKET',
                'status': 'PLACED'
            }
            
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}", exc_info=True)
            return None
