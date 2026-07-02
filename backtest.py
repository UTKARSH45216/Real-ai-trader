"""
Backtesting module - Test Gemini strategy on historical data before live trading.
Uses Zerodha historical data or free data sources.
"""

import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta
import pandas as pd

from config import Settings
from gemini_brain import GeminiBrain

logger = logging.getLogger(__name__)


class BacktestEngine:
    """Backtest trading strategies using historical data."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.gemini_brain = GeminiBrain(settings)
        self.trades = []
        self.portfolio_value = 100000  # Starting capital
        self.cash = 100000
        self.positions = {}
        
    def run_backtest(self, historical_data: Dict[str, pd.DataFrame], start_date: str, end_date: str):
        """
        Run backtest on historical data.
        
        historical_data: Dict of {symbol: DataFrame with OHLCV}
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")
        logger.info(f"Starting capital: ${self.portfolio_value:,.2f}")
        
        # Simulate daily trading cycles
        current_date = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        
        while current_date <= end_date_obj:
            # Skip weekends
            if current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # Get data for current date
            date_str = current_date.strftime("%Y-%m-%d")
            
            # Prepare market data snapshot
            market_data = {}
            for symbol, df in historical_data.items():
                # Find row closest to current date
                row = df[df['date'] <= date_str].iloc[-1:] if len(df[df['date'] <= date_str]) > 0 else None
                
                if row is None or row.empty:
                    continue
                
                row = row.iloc[0]
                market_data[symbol] = {
                    'ohlcv': {
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row['volume'])
                    },
                    'rsi': self._calculate_rsi(df, date_str),
                    'ma20': self._calculate_ma(df, date_str, 20),
                    'change_pct': ((row['close'] - row['open']) / row['open'] * 100) if row['open'] > 0 else 0,
                    'timestamp': date_str
                }
            
            if not market_data:
                current_date += timedelta(days=1)
                continue
            
            # Get Gemini decision
            decision = self.gemini_brain.analyze_patterns(market_data)
            
            # Execute trade
            if decision['decision'] in ['BUY', 'SELL']:
                self._execute_backtest_trade(
                    decision['decision'],
                    decision['reason'],
                    market_data,
                    date_str
                )
            
            # Update portfolio value
            self._update_portfolio_value(market_data, date_str)
            
            current_date += timedelta(days=1)
        
        # Print results
        self._print_backtest_results()
    
    def _calculate_rsi(self, df: pd.DataFrame, date_str: str, period: int = 14) -> float:
        """Calculate RSI for a date."""
        try:
            subset = df[df['date'] <= date_str].tail(period + 1)
            if len(subset) < period:
                return 50.0
            
            closes = subset['close'].values
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            
            gains = sum(d for d in deltas if d > 0) / period if period > 0 else 0
            losses = abs(sum(d for d in deltas if d < 0)) / period if period > 0 else 0
            
            if losses == 0:
                return 100.0
            
            rs = gains / losses
            rsi = 100 - (100 / (1 + rs))
            return round(rsi, 2)
            
        except:
            return 50.0
    
    def _calculate_ma(self, df: pd.DataFrame, date_str: str, period: int) -> float:
        """Calculate moving average for a date."""
        try:
            subset = df[df['date'] <= date_str].tail(period)
            if len(subset) < period:
                return subset['close'].mean()
            
            return round(subset['close'].mean(), 2)
        except:
            return 0.0
    
    def _execute_backtest_trade(self, decision: str, reason: str, market_data: Dict, date: str):
        """Execute a trade in backtest."""
        symbol = self.settings.SYMBOLS_TO_MONITOR[0]
        
        if symbol not in market_data:
            return
        
        price = market_data[symbol]['ohlcv']['close']
        qty = self.settings.ORDER_QUANTITY
        
        if decision == 'BUY':
            cost = price * qty
            if self.cash >= cost:
                self.cash -= cost
                self.positions[symbol] = {
                    'qty': qty,
                    'avg_price': price,
                    'entry_date': date
                }
                self.trades.append({
                    'date': date,
                    'symbol': symbol,
                    'side': 'BUY',
                    'qty': qty,
                    'price': price,
                    'reason': reason
                })
                logger.info(f"[{date}] BUY {symbol} @ ${price:.2f} | {reason[:50]}")
        
        elif decision == 'SELL':
            if symbol in self.positions:
                pos = self.positions[symbol]
                proceeds = price * pos['qty']
                self.cash += proceeds
                profit = proceeds - (pos['avg_price'] * pos['qty'])
                profit_pct = (profit / (pos['avg_price'] * pos['qty']) * 100) if pos['avg_price'] * pos['qty'] > 0 else 0
                
                self.trades.append({
                    'date': date,
                    'symbol': symbol,
                    'side': 'SELL',
                    'qty': pos['qty'],
                    'price': price,
                    'profit': profit,
                    'profit_pct': profit_pct,
                    'reason': reason
                })
                logger.info(f"[{date}] SELL {symbol} @ ${price:.2f} | Profit: ${profit:.2f} ({profit_pct:.2f}%)")
                
                del self.positions[symbol]
    
    def _update_portfolio_value(self, market_data: Dict, date: str):
        """Update portfolio value based on current prices."""
        position_value = 0
        for symbol, pos in self.positions.items():
            if symbol in market_data:
                price = market_data[symbol]['ohlcv']['close']
                position_value += price * pos['qty']
        
        self.portfolio_value = self.cash + position_value
    
    def _print_backtest_results(self):
        """Print backtest statistics."""
        if not self.trades:
            logger.info("No trades executed during backtest")
            return
        
        # Calculate statistics
        buy_trades = [t for t in self.trades if t['side'] == 'BUY']
        sell_trades = [t for t in self.trades if t['side'] == 'SELL']
        
        profitable_trades = [t for t in sell_trades if t['profit'] > 0]
        losing_trades = [t for t in sell_trades if t['profit'] < 0]
        
        total_profit = sum(t.get('profit', 0) for t in self.trades if t['side'] == 'SELL')
        win_rate = (len(profitable_trades) / len(sell_trades) * 100) if sell_trades else 0
        avg_win = sum(t['profit'] for t in profitable_trades) / len(profitable_trades) if profitable_trades else 0
        avg_loss = sum(t['profit'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        return_pct = ((self.portfolio_value - 100000) / 100000 * 100)
        
        logger.info("\n" + "="*60)
        logger.info("BACKTEST RESULTS")
        logger.info("="*60)
        logger.info(f"Total Trades: {len(sell_trades)}")
        logger.info(f"Winning Trades: {len(profitable_trades)}")
        logger.info(f"Losing Trades: {len(losing_trades)}")
        logger.info(f"Win Rate: {win_rate:.1f}%")
        logger.info(f"Average Win: ${avg_win:.2f}")
        logger.info(f"Average Loss: ${avg_loss:.2f}")
        logger.info(f"Total Profit: ${total_profit:.2f}")
        logger.info(f"Final Portfolio Value: ${self.portfolio_value:,.2f}")
        logger.info(f"Return: {return_pct:.2f}%")
        logger.info("="*60)


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # You would load historical data from a data provider
    # Example: using yfinance or Zerodha historical data
    
    settings = Settings()
    backtest = BacktestEngine(settings)
    
    # Load your historical data here
    # backtest.run_backtest(historical_data, "2023-01-01", "2023-12-31")
    
    logger.info("Backtest template ready. Load your historical data to run backtests.")
