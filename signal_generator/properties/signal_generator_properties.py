# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from pydantic import BaseModel

class BaseSignalProps(BaseModel):
    pass

class MACrossoverProps(BaseSignalProps):
    """
    Represents the properties for a Moving Average Crossover signal generator.

    Attributes:
        timeframe (str): The timeframe for the signal generator.
        fast_period (int): The period for the fast moving average.
        slow_period (int): The period for the slow moving average.
    """
    timeframe: str
    fast_period: int
    slow_period: int

class RSIProps(BaseSignalProps):
    timeframe: str
    rsi_period: int
    rsi_upper: float
    rsi_lower: float
    sl_points: int
    tp_points: int


class TrendPullbackProps(BaseSignalProps):
    entry_timeframe: str
    trend_timeframe: str
    trend_fast_period: int
    trend_slow_period: int
    setup_ema_period: int
    rsi_period: int
    rsi_bull_threshold: float
    rsi_bear_threshold: float
    atr_period: int
    sl_atr_mult: float
    tp_atr_mult: float

class SmartMoneySignalProps(BaseSignalProps):
    entry_timeframe: str
    trend_timeframe: str
    trend_fast_period: int
    trend_slow_period: int
    ema_fast_period: int
    ema_slow_period: int
    rsi_period: int
    rsi_bull_threshold: float
    rsi_bear_threshold: float
    macd_fast: int
    macd_slow: int
    macd_signal: int
    fvg_lookback: int
    fib_lookback: int
    atr_period: int
    sl_atr_mult: float
    tp_atr_mult: float
    min_liquidity_gap_points: float = 0.0
    use_fibonacci: bool = True
    use_fvg: bool = True
    use_macd: bool = True

class BollingerBandsProps(BaseSignalProps):
    entry_timeframe: str
    bb_period: int = 20
    bb_std_dev: float = 2.0
    squeeze_threshold_pct: float = 0.05
    squeeze_lookback: int = 20
    walk_basis_points: int = 50
    walk_min_candles: int = 3
    reversal_exit_std: float = 0.5
    atr_period: int = 14
    sl_atr_mult: float = 1.2
    tp_atr_mult: float = 2.0
    min_squeeze_duration: int = 5
    volatility_regime_threshold: float = 0.10
