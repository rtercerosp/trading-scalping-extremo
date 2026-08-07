# config.py

"""
Archivo de Configuración Central para el Proyecto de Trading.

Este archivo consolida todos los parámetros configurables del sistema
para facilitar su gestión, auditoría y modificación.
"""

from datetime import timedelta

# --- 1. CONFIGURACIÓN GENERAL DE TRADING ---
MAGIC_NUMBER: int = 20260728 # Mantener el mismo Magic Number para la misma base de estrategia
STRATEGY_VERSION: str = "V10_ZERO_LOSS_SCALPING"

# Lista de símbolos por defecto. Puede ser sobreescrita por la variable de entorno TRADING_SYMBOLS.
DEFAULT_SYMBOLS: list[str] = ["BTCUSDc", "XAUUSDc", "ETHUSDc", "EURUSDc"]

# --- 2. CONFIGURACIÓN DE TIMEFRAMES ---
ENTRY_TIMEFRAME: str = "5min"
TREND_TIMEFRAME: str = "15min"

# --- 3. CONFIGURACIÓN DEL BACKTESTING (usado en run_preload.py) ---
BACKTEST_DAYS: int = 30
BACKTEST_TIMEFRAME: str = "5min"

# --- 4. CONFIGURACIÓN DE LA CARTERA (PORTFOLIO) ---
PORTFOLIO_MAX_TOTAL_POSITIONS: int = 12
PORTFOLIO_MAX_POSITIONS_PER_SYMBOL: int = 3
PORTFOLIO_MAX_POSITIONS_BY_SYMBOL: dict[str, int] = {
    "BTCUSD": 3, "ETHUSD": 3, "XAUUSD": 3, "EURUSD": 3
}
PORTFOLIO_MAX_POSITIONS_BY_CATEGORY: dict[str, int] = {
    "crypto": 6, "gold": 3, "forex": 3
}

# --- 5. CONFIGURACIÓN DEL GESTOR DE RIESGO ---
RISK_MAX_LEVERAGE_FACTOR: int = 4

# --- 6. CONFIGURACIÓN DEL SIZER DE POSICIÓN ---
SIZER_DEFAULT_RISK_PCT: float = 0.015

# --- 6b. CONFIGURACIÓN DE SCALPING EXTREMO POR ACTIVO ---
EXTREME_SCALPING_PARAMS: dict[str, dict] = {
    "BTCUSD": {
        "enabled": True,
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 2.2,
        "risk_pct": 0.003,
        "trailing_activation_pct": 0.002,
        "trailing_offset_pct": 0.0015,
        "min_win_rate_for_trading": 0.50,
        "exclude_if_win_rate_below": 0.40,
    },
    "ETHUSD": {
        "enabled": True,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 3.5,
        "risk_pct": 0.008,
        "trailing_activation_pct": 0.002,
        "trailing_offset_pct": 0.0015,
        "min_win_rate_for_trading": 0.45,
        "exclude_if_win_rate_below": 0.38,
    },
    "EURUSD": {
        "enabled": True,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.007,
        "trailing_activation_pct": 0.0015,
        "trailing_offset_pct": 0.001,
        "min_win_rate_for_trading": 0.55,
        "exclude_if_win_rate_below": 0.45,
    },
    "XAUUSD": {
        "enabled": True,
        "sl_atr_mult": 0.7,
        "tp_atr_mult": 3.5,
        "risk_pct": 0.010,
        "trailing_activation_pct": 0.003,
        "trailing_offset_pct": 0.002,
        "min_win_rate_for_trading": 0.50,
        "exclude_if_win_rate_below": 0.42,
    },
    "GBPUSD": {
        "enabled": True,
        "sl_atr_mult": 0.85,
        "tp_atr_mult": 2.4,
        "risk_pct": 0.008,
        "trailing_activation_pct": 0.0022,
        "trailing_offset_pct": 0.0016,
        "min_win_rate_for_trading": 0.52,
        "exclude_if_win_rate_below": 0.42,
        "priority": 3,
    },
    "USDJPY": {
        "enabled": True,
        "sl_atr_mult": 0.85,
        "tp_atr_mult": 2.2,
        "risk_pct": 0.007,
        "trailing_activation_pct": 0.002,
        "trailing_offset_pct": 0.0015,
        "min_win_rate_for_trading": 0.53,
        "exclude_if_win_rate_below": 0.43,
        "priority": 4,
    },
}

# --- 6b-II. CONFIGURACIÓN V10 ZERO LOSS SCALPING ---
V10_ZERO_LOSS_ENABLED: bool = True
V10_BREAK_EVEN_TRIGGER_PCT: float = 0.30
V10_BREAK_EVEN_MIN_TRIGGER_POINTS: dict[str, int] = {
    "EURUSD": 12,
    "EURUSDc": 12,
    "GBPUSD": 18,
    "GBPUSDc": 18,
    "USDJPY": 15,
    "USDJPYc": 15,
    "XAUUSD": 3000,
    "XAUUSDc": 3000,
    "ETHUSD": 60,
    "ETHUSDc": 60,
    "BTCUSD": 100,
    "BTCUSDc": 100,
}
V10_BREAK_EVEN_MAX_TRIGGER_POINTS: dict[str, int] = {
    "EURUSD": 60,
    "EURUSDc": 60,
    "GBPUSD": 80,
    "GBPUSDc": 80,
    "USDJPY": 80,
    "USDJPYc": 80,
    "XAUUSD": 6000,
    "XAUUSDc": 6000,
    "ETHUSD": 200,
    "ETHUSDc": 200,
    "BTCUSD": 500,
    "BTCUSDc": 500,
}
V10_BROKER_COST_COVERAGE: dict[str, dict] = {
    "EURUSD": {"spread_points": 8, "commission_per_lot": 0.0, "min_profit_points": 3},
    "EURUSDc": {"spread_points": 8, "commission_per_lot": 0.0, "min_profit_points": 3},
    "GBPUSD": {"spread_points": 12, "commission_per_lot": 0.0, "min_profit_points": 4},
    "GBPUSDc": {"spread_points": 12, "commission_per_lot": 0.0, "min_profit_points": 4},
    "USDJPY": {"spread_points": 10, "commission_per_lot": 0.0, "min_profit_points": 15},
    "USDJPYc": {"spread_points": 10, "commission_per_lot": 0.0, "min_profit_points": 15},
    "XAUUSD": {"spread_points": 250, "commission_per_lot": 0.0, "min_profit_points": 50},
    "XAUUSDc": {"spread_points": 250, "commission_per_lot": 0.0, "min_profit_points": 50},
    "ETHUSD": {"spread_points": 80, "commission_per_lot": 0.0, "min_profit_points": 30},
    "ETHUSDc": {"spread_points": 80, "commission_per_lot": 0.0, "min_profit_points": 30},
    "BTCUSD": {"spread_points": 500, "commission_per_lot": 0.0, "min_profit_points": 100},
    "BTCUSDc": {"spread_points": 500, "commission_per_lot": 0.0, "min_profit_points": 100},
}
V10_REVERSE_PROTECTION_PCT: float = 0.25
V10_GAP_PROTECTION_PCT: float = 0.003
V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT: float = 0.15
V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT: float = 0.003
V10_TRAILING_AGGRESSIVE_OFFSET_POINTS: dict[str, int] = {
    "EURUSD": 15,
    "EURUSDc": 15,
    "GBPUSD": 20,
    "GBPUSDc": 20,
    "USDJPY": 100,
    "USDJPYc": 100,
    "XAUUSD": 500,
    "XAUUSDc": 500,
    "ETHUSD": 50,
    "ETHUSDc": 50,
    "BTCUSD": 200,
    "BTCUSDc": 200,
}
V10_COMPOUNDING_VOLUME_MULTIPLIER: float = 2.0
V10_COMPOUNDING_MIN_EQUITY: float = 5000.0
V10_SPREAD_MAX_POINTS_MULTIPLIER: float = 1.5
V10_MIN_BROKER_COVERAGE_POINTS: int = 2
V10_MAX_VOLUME_PER_CANDLE_RATIO: float = 0.05
V10_SPREAD_FILTER_BY_SYMBOL: dict[str, dict] = {
    "EURUSD": {"min_broker_coverage_points": 10, "multiplier": 2.5},
    "EURUSDc": {"min_broker_coverage_points": 10, "multiplier": 2.5},
    "GBPUSD": {"min_broker_coverage_points": 15, "multiplier": 2.5},
    "GBPUSDc": {"min_broker_coverage_points": 15, "multiplier": 2.5},
    "USDJPY": {"min_broker_coverage_points": 15, "multiplier": 2.5},
    "USDJPYc": {"min_broker_coverage_points": 15, "multiplier": 2.5},
    "XAUUSD": {"min_broker_coverage_points": 300, "multiplier": 2.0},
    "XAUUSDc": {"min_broker_coverage_points": 300, "multiplier": 2.0},
    "ETHUSD": {"min_broker_coverage_points": 100, "multiplier": 2.5},
    "ETHUSDc": {"min_broker_coverage_points": 100, "multiplier": 2.5},
    "BTCUSD": {"min_broker_coverage_points": 500, "multiplier": 2.0},
    "BTCUSDc": {"min_broker_coverage_points": 500, "multiplier": 2.0},
}

# --- 6c. CONFIGURACIÓN DE ESTRATEGIA FIBONACCI SCALP ---
FIB_SCALP_MIN_CONFIDENCE: float = 0.65
FIB_SCALP_LOOKBACK: int = 20
FIB_SCALP_TP1_MULT: float = 0.618
FIB_SCALP_TP2_MULT: float = 1.618
FIB_SCALP_SL_BUFFER_POINTS: int = 5

# --- 7. CONFIGURACIÓN DE LA IA (TRADING AI) ---

# 7.1. Parámetros del Sistema de Cuarentena (StrategySelector)
PROBATION_PROFIT_FACTOR_THRESHOLD: float = 0.80
PROBATION_MIN_TRADES: int = 15
PROBATION_DURATION: timedelta = timedelta(minutes=50) # Mantener la misma duración de cuarentena

# 7.2. Parámetros por Defecto del Motor de Aprendizaje (LearningEngine)
LEARNING_DEFAULT_SL_ATR_MULT: float = 0.8
LEARNING_DEFAULT_TP_ATR_MULT: float = 3.5
LEARNING_DEFAULT_RISK_PCT: float = 0.015
LEARNING_DEFAULT_LEARNING_RATE: float = 0.1

# 7.3. Calibración Específica por Activo (LearningEngine)
LEARNING_ASSET_SPECIFIC_PARAMS: dict[str, dict] = {
    "BTCUSD": {
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 2.2,
        "risk_pct": 0.003,
    },
    "EURUSD": {
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.007,
    },
    "ETHUSD": {
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 3.5,
        "risk_pct": 0.008,
    },
    "XAUUSD": {
        "sl_atr_mult": 0.7,
        "tp_atr_mult": 3.5,
        "risk_pct": 0.010,
    }
}

# 7.4. Límites y Pasos del Motor de Aprendizaje (LearningEngine)
LEARNING_SL_ATR_MULT_MIN: float = 0.5
LEARNING_SL_ATR_MULT_MAX: float = 2.0
LEARNING_TP_ATR_MULT_MIN: float = 1.2
LEARNING_TP_ATR_MULT_MAX: float = 5.0
LEARNING_RISK_PCT_MIN: float = 0.0025
LEARNING_RISK_PCT_MAX: float = 0.02

LEARNING_STEP_SL_DECREASE: float = 0.08
LEARNING_STEP_TP_DECREASE: float = 0.05
LEARNING_STEP_RISK_DECREASE: float = 0.001
LEARNING_STEP_SL_INCREASE: float = 0.05
LEARNING_STEP_TP_INCREASE: float = 0.1
LEARNING_STEP_RISK_INCREASE: float = 0.0005
LEARNING_WIN_RATE_THRESHOLD_FOR_RISK_INCREASE: float = 0.6

# --- 8. CONFIGURACIÓN DE ESTRATEGIAS (SignalGenerator) ---

# 8.1. Parámetros por defecto para SmartMoney
SMART_MONEY_DEFAULT_PROPS: dict = {
    "trend_fast_period": 10,
    "trend_slow_period": 20,
    "ema_fast_period": 9,
    "ema_slow_period": 21,
    "rsi_period": 14,
    "rsi_bull_threshold": 52.0,
    "rsi_bear_threshold": 48.0,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "fvg_lookback": 20,
    "fib_lookback": 30,
    "atr_period": 14,
}