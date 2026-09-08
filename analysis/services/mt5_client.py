"""
MT5 Client Service - Handles MetaTrader 5 connection and trade execution.
Ported from standalone script with integration for Django system.
"""
import logging
import os
from typing import Optional, Tuple

try:
    import MetaTrader5 as mt5
    _HAS_MT5 = True
except ImportError:
    _HAS_MT5 = False
    logging.warning("MetaTrader5 not installed. MT5 functionality will be disabled.")

from django.conf import settings

logger = logging.getLogger(__name__)

# MT5 Configuration
MT5_PATH = getattr(settings, 'MT5_PATH', r"C:\Program Files\MetaTrader 5 Terminal\terminal64.exe")
MT5_LOGIN = getattr(settings, 'MT5_LOGIN', 25305222)
MT5_PASSWORD = getattr(settings, 'MT5_PASSWORD', "Kiburu2s.")
MT5_SERVER = getattr(settings, 'MT5_SERVER', "Deriv-Demo")

# Risk Management Constants
MICRO_ACCOUNT_MAX_BALANCE = 50
SMALL_ACCOUNT_MAX_BALANCE = 200
MAX_RISK_PCT_MICRO = 0.5
MAX_RISK_PCT_SMALL = 1.0
MAX_RISK_PCT_NORMAL = 1.0
MAX_RISK_PCT_IF_MIN_LOT = 1.5
MAX_POSITIONS = 3
MAX_POSITIONS_PER_MARKET = 1
MIN_RISK_REWARD = 1.5

# Position Management
USE_TRAILING_STOP = False  # Disabled by default for stability


class MT5Client:
    """Handles MT5 connection and trade execution."""
    
    def __init__(self):
        self.initialized = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self._connection = None
        
    def initialize(self) -> bool:
        """Initialize MT5 connection. Returns False if MT5 is not available or fails."""
        if not _HAS_MT5:
            logger.info("MT5 not installed. Using paper trading only.")
            return False
            
        try:
            mt5.shutdown()
            
            # Try connecting to already running MT5 terminal
            logger.info("Trying to connect to running MT5 terminal...")
            if mt5.initialize(
                login=MT5_LOGIN,
                password=MT5_PASSWORD,
                server=MT5_SERVER,
                timeout=30000
            ):
                account_info = mt5.account_info()
                if account_info is not None:
                    logger.info(f"MT5 Connected (LIVE) - Balance: {account_info.balance}")
                    self.initialized = True
                    return True
                mt5.shutdown()
            else:
                logger.info("MT5 not available. Using paper trading only.")
                mt5.shutdown()
            
            # Try starting MT5 from path
            if os.path.exists(MT5_PATH):
                logger.info(f"Trying MT5 at: {MT5_PATH}")
                if mt5.initialize(
                    path=MT5_PATH,
                    login=MT5_LOGIN,
                    password=MT5_PASSWORD,
                    server=MT5_SERVER,
                    timeout=30000
                ):
                    account_info = mt5.account_info()
                    if account_info is not None:
                        logger.info(f"MT5 Connected (LIVE) - Balance: {account_info.balance}")
                        self.initialized = True
                        return True
                    mt5.shutdown()
                else:
                    err = mt5.last_error()
                    logger.info(f"MT5 init failed: {err}. Using paper trading only.")
                    mt5.shutdown()
            
            logger.info("MT5 initialization failed. Using paper trading only.")
            return False
            
        except Exception as e:
            logger.info(f"MT5 initialization error: {e}. Using paper trading only.")
            return False
    
    def check_connection(self) -> bool:
        """Check if MT5 connection is still active."""
        if not self.initialized:
            return False
            
        try:
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Lost MT5 connection")
                self.initialized = False
                return False
            return True
        except Exception as e:
            logger.error(f"Connection check error: {e}")
            return False
    
    def get_position_count(self) -> int:
        """Get count of open positions opened by this bot (magic 234000)."""
        if not self.check_connection():
            return 0
            
        try:
            positions = mt5.positions_get()
            if positions is None:
                return 0
            return len([p for p in positions if getattr(p, 'magic', 0) == 234000])
        except Exception:
            return 0
    
    def get_position_count_by_market(self, symbol: str) -> int:
        """Get count of open positions for a specific market."""
        if not self.check_connection():
            return 0
            
        try:
            positions = mt5.positions_get()
            if positions is None:
                return 0
            return len([p for p in positions if getattr(p, 'magic', 0) == 234000 and p.symbol == symbol])
        except Exception:
            return 0
    
    def map_deriv_to_mt5_symbol(self, deriv_symbol: str) -> str:
        """Map Deriv symbol to MT5 symbol format."""
        mapping = {
            # Volatility indices
            '1HZ10V': 'Volatility 10 (1s) Index',
            '1HZ25V': 'Volatility 25 (1s) Index',
            '1HZ50V': 'Volatility 50 (1s) Index',
            '1HZ75V': 'Volatility 75 (1s) Index',
            '1HZ100V': 'Volatility 100 (1s) Index',
            'R_75': 'Volatility 75 Index',
            'R_100': 'Volatility 100 Index',
            'R_50': 'Volatility 50 Index',
            'R_25': 'Volatility 25 Index',
            'R_10': 'Volatility 10 Index',
            # Synthetic indices
            'BOOM_1000': 'Boom 1000 Index',
            'BOOM_500': 'Boom 500 Index',
            'CRASH_1000': 'Crash 1000 Index',
            'CRASH_500': 'Crash 500 Index',
            'Jump_75': 'Jump 75 Index',
            'Jump_100': 'Jump 100 Index',
            'Jump_50': 'Jump 50 Index',
            'STPRD': 'Step Index',
            # Forex pairs
            'frxGBPJPY': 'GBPJPY',
            'frxEURUSD': 'EURUSD',
            'frxUSDJPY': 'USDJPY',
            'frxGBPUSD': 'GBPUSD',
            'frxEURGBP': 'EURGBP',
            'frxAUDUSD': 'AUDUSD',
            'frxNZDUSD': 'NZDUSD',
            'frxUSDCAD': 'USDCAD',
            'frxEURAUD': 'EURAUD',
            'frxAUDJPY': 'AUDJPY',
            'frxEURJPY': 'EURJPY',
            'frxUSDCHF': 'USDCHF',
            'frxEURCHF': 'EURCHF',
            # Commodities
            'frxXAUUSD': 'XAUUSD',
            'frxXAGUSD': 'XAGUSD',
            'frxXPTUSD': 'XPTUSD',
            'frxXPDUSD': 'XPDUSD',
            'frxWTI': 'WTI',
            'frxBRENT': 'BRENT',
            'frxNATGAS': 'NATGAS',
        }
        
        return mapping.get(deriv_symbol, deriv_symbol)
    
    def calculate_position_size(self, balance: float, entry_price: float, stop_loss: float, symbol_info) -> Tuple[Optional[float], float]:
        """
        Calculate position size based on account balance and risk.
        Returns (volume, risk_pct_used) or (None, None) if trade would risk too much.
        """
        try:
            sl_distance = abs(entry_price - stop_loss)
            if sl_distance <= 0:
                return symbol_info.volume_min, 0.0
                
            contract_size = getattr(symbol_info, 'trade_contract_size', 100000)
            if contract_size <= 0:
                contract_size = 100000
                
            min_volume = symbol_info.volume_min
            max_volume = symbol_info.volume_max
            volume_step = symbol_info.volume_step
            
            # Determine risk percentage based on account size
            if balance < MICRO_ACCOUNT_MAX_BALANCE:
                risk_pct = MAX_RISK_PCT_MICRO
            elif balance < SMALL_ACCOUNT_MAX_BALANCE:
                risk_pct = MAX_RISK_PCT_SMALL
            else:
                risk_pct = MAX_RISK_PCT_NORMAL
            
            risk_amount = balance * (risk_pct / 100)
            volume = risk_amount / (contract_size * sl_distance)
            volume = max(min_volume, min(volume, max_volume))
            volume = round(round(volume / volume_step) * volume_step, 2)
            
            if volume < volume_step:
                volume = min_volume
            
            actual_risk_amount = volume * contract_size * sl_distance
            actual_risk_pct = (actual_risk_amount / balance) * 100 if balance > 0 else 0
            
            # Skip trade if min lot would risk too much for micro account
            if balance < MICRO_ACCOUNT_MAX_BALANCE and volume == min_volume and actual_risk_pct > MAX_RISK_PCT_IF_MIN_LOT:
                logger.warning(
                    "Skip trade: min lot would risk %.1f%% of $%.2f account (max %.1f%%).",
                    actual_risk_pct, balance, MAX_RISK_PCT_IF_MIN_LOT
                )
                return None, None
                
            return volume, actual_risk_pct
            
        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return None, None
    
    def execute_trade(self, signal: dict) -> bool:
        """Execute live trade on MT5 based on signal."""
        if not _HAS_MT5:
            logger.error("MT5 not installed. Cannot execute trade.")
            return False
            
        try:
            # Check position limits
            if self.get_position_count() >= MAX_POSITIONS:
                logger.warning(f"Position limit reached ({self.get_position_count()}/{MAX_POSITIONS})")
                return False
                
            if self.get_position_count_by_market(signal['symbol']) >= MAX_POSITIONS_PER_MARKET:
                logger.warning(f"Market position limit reached for {signal['symbol']}")
                return False
            
            # Ensure MT5 is initialized
            if not self.initialized:
                if not self.initialize():
                    return False
            
            # Map symbol for MT5
            mt5_symbol = self.map_deriv_to_mt5_symbol(signal['symbol'])
            
            # Get symbol info
            symbol_info = mt5.symbol_info(mt5_symbol)
            if symbol_info is None:
                logger.error(f"Symbol {mt5_symbol} not found")
                return False
            
            # Enable symbol for trading
            if not symbol_info.visible:
                if not mt5.symbol_select(mt5_symbol, True):
                    logger.error(f"Failed to select {mt5_symbol}")
                    return False
            
            # Get current price
            tick = mt5.symbol_info_tick(mt5_symbol)
            if tick is None:
                logger.error(f"Failed to get price for {mt5_symbol}")
                return False
            
            # Set order type and price
            order_type = mt5.ORDER_TYPE_BUY if signal['direction'] == 'Buy' else mt5.ORDER_TYPE_SELL
            price = tick.ask if signal['direction'] == 'Buy' else tick.bid
            
            # Calculate position size
            account_info = mt5.account_info()
            if account_info is None:
                logger.error("Failed to get account info")
                return False
                
            balance = account_info.balance
            volume, risk_pct_used = self.calculate_position_size(
                balance, price, float(signal['stop_loss']), symbol_info
            )
            
            if volume is None:
                return False
            
            # Prepare trade request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": mt5_symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": float(signal['stop_loss']),
                "tp": float(signal['take_profit']),
                "deviation": 10,
                "magic": 234000,
                "comment": f"Signal Strength: {signal.get('signal_strength', 0):.2f}",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_FOK,
            }
            
            # Log trade attempt
            logger.info(f"""
            Executing Live Trade:
            Symbol: {mt5_symbol}
            Type: {signal['direction']}
            Volume: {volume}
            Price: {price}
            SL: {signal['stop_loss']}
            TP: {signal['take_profit']}
            Risk: {risk_pct_used:.2f}%
            """)
            
            # Send order
            result = mt5.order_send(request)
            if resultretcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Order failed: {result.comment}")
                logger.error(f"Error code: {result.retcode}")
                return False
            
            logger.info(f"""
            Live Trade Executed:
            Ticket: {result.order}
            Symbol: {mt5_symbol}
            Volume: {volume}
            Price: {price}
            """)
            
            return True
            
        except Exception as e:
            logger.error(f"Error executing live trade: {e}")
            return False
    
    def shutdown(self):
        """Shutdown MT5 connection."""
        if _HAS_MT5:
            mt5.shutdown()
            self.initialized = False


# Global MT5 client instance
mt5_client = MT5Client()
