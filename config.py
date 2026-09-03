# config.py

"""
Archivo de Configuración Central para el Proyecto de Trading.

Este archivo consolida todos los parámetros configurables del sistema
para facilitar su gestión, auditoría y modificación.
"""

from datetime import timedelta

# --- 1. CONFIGURACIÓN GENERAL DE TRADING ---
MAGIC_NUMBER: int = 20260728 # Mantener el mismo Magic Number para la misma base de estrategia
STRATEGY_VERSION: str = "V14_DIVERSIFIED_RISK_MANAGED"
RESEARCH_MODE: bool = True

# Lista de símbolos por defecto. Puede ser sobreescrita por la variable de entorno TRADING_SYMBOLS.
DEFAULT_SYMBOLS: list[str] = ["XAUUSDc", "EURUSDc", "USDJPYc", "US500", "USTEC", "BTCUSDc", "US30", "ETHUSDc", "UKOIL"]

# --- 2. CONFIGURACIÓN DE TIMEFRAMES ---
ENTRY_TIMEFRAME: str = "5min"
TREND_TIMEFRAME: str = "15min"

# --- 3. CONFIGURACIÓN DEL BACKTESTING (usado en run_preload.py) ---
BACKTEST_DAYS: int = 30
BACKTEST_TIMEFRAME: str = "5min"

# --- 4. CONFIGURACIÓN DE LA CARTERA (PORTFOLIO) ---
PORTFOLIO_MAX_TOTAL_POSITIONS: int = 12
PORTFOLIO_MAX_POSITIONS_PER_SYMBOL: int = 2
PORTFOLIO_MAX_POSITIONS_BY_SYMBOL: dict[str, int] = {
    "BTCUSD": 2, "ETHUSD": 2, "XAUUSD": 2, "EURUSD": 2,
    "USDJPY": 2, "US500": 2, "USTEC": 2, "US30": 2, "UKOIL": 2
}
PORTFOLIO_MAX_POSITIONS_BY_CATEGORY: dict[str, int] = {
    "crypto": 4, "gold": 3, "forex": 4, "index": 4, "commodity": 2
}
PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE: float = 0.50

# --- 5. CONFIGURACIÓN DEL GESTOR DE RIESGO ---
RISK_MAX_LEVERAGE_FACTOR: int = 4

# --- 6. CONFIGURACIÓN DEL SIZER DE POSICIÓN ---
SIZER_DEFAULT_RISK_PCT: float = 0.020

# --- 6a. CONFIGURACIÓN KELLY CRITERION SIZER ---
USE_KELLY_SIZER: bool = True  # Set True to enable Kelly Criterion dynamic sizing
KELLY_FRACTION: float = 0.25   # Fraction of full Kelly (0.25 = Quarter Kelly)
KELLY_MIN_WIN_RATE: float = 0.35  # Minimum win rate to enable Kelly
KELLY_MIN_TRADES: int = 30        # Minimum trades for statistical validity
KELLY_VOLATILITY_LOOKBACK: int = 20  # Periods for volatility estimation

# --- 6b. CONFIGURACIÓN DE SCALPING EXTREMO POR ACTIVO ---
EXTREME_SCALPING_PARAMS: dict[str, dict] = {
    "BTCUSD": {
        "enabled": True,
        "sl_atr_mult": 0.5,
        "tp_atr_mult": 3.0,
        "risk_pct": 0.015,
        "trailing_activation_pct": 0.0009,
        "trailing_offset_pct": 0.0007,
        "min_win_rate_for_trading": 0.48,
        "exclude_if_win_rate_below": 0.40,
    },
    "ETHUSD": {
        "enabled": True,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.5,
        "risk_pct": 0.014,
        "trailing_activation_pct": 0.0010,
        "trailing_offset_pct": 0.0008,
        "min_win_rate_for_trading": 0.45,
        "exclude_if_win_rate_below": 0.38,
    },
    "EURUSD": {
        "enabled": True,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.010,
        "trailing_activation_pct": 0.001,
        "trailing_offset_pct": 0.0008,
        "min_win_rate_for_trading": 0.55,
        "exclude_if_win_rate_below": 0.45,
    },
    "XAUUSD": {
        "enabled": True,
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 2.5,
        "risk_pct": 0.006,
        "trailing_activation_pct": 0.0025,
        "trailing_offset_pct": 0.002,
        "min_win_rate_for_trading": 0.40,
        "exclude_if_win_rate_below": 0.35,
    },
    "GBPUSD": {
        "enabled": True,
        "sl_atr_mult": 0.85,
        "tp_atr_mult": 2.4,
        "risk_pct": 0.010,
        "trailing_activation_pct": 0.0018,
        "trailing_offset_pct": 0.0012,
        "min_win_rate_for_trading": 0.52,
        "exclude_if_win_rate_below": 0.42,
        "priority": 3,
    },
    "USDJPY": {
        "enabled": True,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 1.8,
        "risk_pct": 0.005,
        "trailing_activation_pct": 0.0020,
        "trailing_offset_pct": 0.0015,
        "min_win_rate_for_trading": 0.42,
        "exclude_if_win_rate_below": 0.38,
        "priority": 4,
    },
    "US500": {
        "enabled": True,
        "sl_atr_mult": 0.9,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.008,
        "trailing_activation_pct": 0.0015,
        "trailing_offset_pct": 0.001,
        "min_win_rate_for_trading": 0.52,
        "exclude_if_win_rate_below": 0.42,
    },
    "USTEC": {
        "enabled": True,
        "sl_atr_mult": 1.3,
        "tp_atr_mult": 2.5,
        "risk_pct": 0.004,
        "trailing_activation_pct": 0.0025,
        "trailing_offset_pct": 0.002,
        "min_win_rate_for_trading": 0.30,
        "exclude_if_win_rate_below": 0.25,
    },
    "US30": {
        "enabled": True,
        "sl_atr_mult": 0.9,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.008,
        "trailing_activation_pct": 0.0015,
        "trailing_offset_pct": 0.001,
        "min_win_rate_for_trading": 0.52,
        "exclude_if_win_rate_below": 0.42,
    },
    "UKOIL": {
        "enabled": True,
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.4,
        "risk_pct": 0.010,
        "trailing_activation_pct": 0.0015,
        "trailing_offset_pct": 0.001,
        "min_win_rate_for_trading": 0.50,
        "exclude_if_win_rate_below": 0.40,
    },
}

# --- 6b-I. SELECCION PRIMARIA DE ESTRATEGIA POR ACTIVO ---
ASSET_ALLOWED_STRATEGIES: dict[str, list[str]] = {
    "BTCUSD": ["SignalBTCExtreme", "SignalBTCStructureBreakout", "SignalMomentum", "SignalBreakout"],
    "ETHUSD": ["SignalSmartMoneyETH", "SignalMomentum", "SignalETHStructureBreakout", "SignalBreakout"],
    "XAUUSD": ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout"],
    "EURUSD": ["SignalEURUSDExtreme", "SignalSmartMoneyEURUSD", "SignalTrendPullback", "SignalFibScalp"],
    "USDJPY": ["SignalUSDJPExtreme", "SignalMomentum", "SignalBreakout"],
    "US30": ["SignalBollingerBands", "SignalBreakout", "SignalTrendPullback"],
    "US500": ["SignalTrendPullback", "SignalBreakout", "SignalCandlestickPatterns"],
    "USTEC": ["SignalBollingerBands", "SignalTrendPullback"],
    "UKOIL": ["SignalTrendPullback", "SignalBollingerBands"],
}
ASSET_PRIMARY_STRATEGIES: dict[str, list[str]] = {
    "BTCUSD": ["SignalBTCExtreme", "SignalBTCStructureBreakout", "SignalMomentum", "SignalBreakout"],
    "ETHUSD": ["SignalSmartMoneyETH", "SignalMomentum", "SignalETHStructureBreakout", "SignalBreakout"],
    "XAUUSD": ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout"],
    "EURUSD": ["SignalEURUSDExtreme", "SignalSmartMoneyEURUSD", "SignalTrendPullback", "SignalFibScalp"],
    "USDJPY": ["SignalUSDJPExtreme", "SignalMomentum", "SignalBreakout"],
    "US30": ["SignalBollingerBands", "SignalBreakout", "SignalTrendPullback"],
    "US500": ["SignalTrendPullback", "SignalBreakout", "SignalCandlestickPatterns"],
    "USTEC": ["SignalBollingerBands", "SignalTrendPullback"],
    "UKOIL": ["SignalTrendPullback", "SignalBollingerBands"],
}
ASSET_STRATEGY_MAX_CANDIDATES: dict[str, int] = {
    "BTCUSD": 3,
    "ETHUSD": 3,
    "XAUUSD": 2,
    "EURUSD": 3,
    "USDJPY": 2,
    "US30": 3,
    "US500": 3,
    "USTEC": 2,
    "UKOIL": 2,
}
ASSET_SIGNAL_COOLDOWN_MINUTES: dict[str, int] = {
    "BTCUSD": 30,
    "ETHUSD": 20,
    "XAUUSD": 45,
    "EURUSD": 20,
    "USDJPY": 20,
    "US30": 30,
    "US500": 30,
    "USTEC": 30,
    "UKOIL": 30,
}
V13_QUALITY_THRESHOLD_DEFAULT: float = 60.0
V13_QUALITY_THRESHOLD_BY_SYMBOL: dict[str, float] = {
    "BTCUSD": 68.0,
    "ETHUSD": 66.0,
    "XAUUSD": 72.0,
    "EURUSD": 64.0,
    "USDJPY": 63.0,
    "US30": 64.0,
    "US500": 64.0,
    "USTEC": 66.0,
    "UKOIL": 64.0,
}
V13_CONSENSUS_THRESHOLD_DEFAULT: int = 1
V13_CONSENSUS_THRESHOLD_BY_SYMBOL: dict[str, int] = {
    "BTCUSD": 1,
    "ETHUSD": 1,
    "XAUUSD": 1,
    "EURUSD": 1,
    "USDJPY": 1,
    "US30": 1,
    "US500": 1,
    "USTEC": 1,
    "UKOIL": 1,
}

# --- 6c. CONFIGURACIÓN DE CIRCUIT BREAKER POR ACTIVO ---
ASSET_CIRCUIT_BREAKER_ENABLED: bool = True
ASSET_DRAWDOWN_WARNING_PCT: float = -0.08
ASSET_DRAWDOWN_BREAKER_PCT: float = -0.15
ASSET_DRAWDOWN_EXCLUDE_PCT: float = -0.20
ASSET_MAX_CONSECUTIVE_LOSSES: int = 3
ASSET_MIN_TRADES_FOR_BREAKER: int = 8
ASSET_MIN_WIN_RATE_GLOBAL: float = 0.40
ASSET_BREAKER_COOLDOWN_SECONDS: int = 7200
ASSET_RESET_DRAWDOWN_ON_NEW_DAY: bool = True

# --- 6d. CONFIGURACIÓN DE BOOST POR MEJOR ACTIVO ---
ASSET_BOOST_ENABLED: bool = True
ASSET_BOOST_TOP_N: int = 2                    # Cantidad de activos top a boostear
ASSET_BOOST_MAX_POSITIONS_MULTIPLIER: float = 1.2   # Multiplicador de posiciones para el mejor activo
ASSET_BOOST_RISK_MULTIPLIER: float = 1.15            # Multiplicador de riesgo para el mejor activo
ASSET_BOOST_MIN_TRADES: int = 10             # Mínimo de trades para considerar boost
ASSET_BOOST_MIN_WIN_RATE: float = 0.55       # Win rate mínimo para ser candidato a boost
ASSET_BOOST_MIN_PROFIT: float = 15.0         # Ganancia mínima total para ser candidato
ASSET_BOOST_COOLDOWN_SECONDS: int = 180      # 3 minutos entre reevaluaciones de boost
ASSET_BOOST_WHITELIST: list[str] = ["BTCUSD", "ETHUSD", "XAUUSD", "US30"]  # Solo estos activos pueden ser top performers

# --- 6b-II. CONFIGURACIÓN V10 ZERO LOSS SCALPING ---
V10_ZERO_LOSS_ENABLED: bool = True
V10_BREAK_EVEN_TRIGGER_PCT: float = 0.10
V10_BREAK_EVEN_MIN_TRIGGER_POINTS: dict[str, int] = {
    "EURUSD": 8,
    "EURUSDc": 8,
    "GBPUSD": 12,
    "GBPUSDc": 12,
    "USDJPY": 10,
    "USDJPYc": 10,
    "XAUUSD": 200,
    "XAUUSDc": 200,
    "US500": 15,
    "USTEC": 15,
    "US30": 20,
    "ETHUSD": 15,
    "ETHUSDc": 15,
    "BTCUSD": 50,
    "BTCUSDc": 50,
    "UKOIL": 15,
}
V10_BREAK_EVEN_MAX_TRIGGER_POINTS: dict[str, int] = {
    "EURUSD": 30,
    "EURUSDc": 30,
    "GBPUSD": 40,
    "GBPUSDc": 40,
    "USDJPY": 40,
    "USDJPYc": 40,
    "XAUUSD": 2000,
    "XAUUSDc": 2000,
    "US500": 500,
    "USTEC": 500,
    "US30": 800,
    "ETHUSD": 80,
    "ETHUSDc": 80,
    "BTCUSD": 250,
    "BTCUSDc": 250,
    "UKOIL": 400,
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
    "US500": {"spread_points": 20, "commission_per_lot": 0.0, "min_profit_points": 5},
    "USTEC": {"spread_points": 30, "commission_per_lot": 0.0, "min_profit_points": 8},
    "US30": {"spread_points": 30, "commission_per_lot": 0.0, "min_profit_points": 10},
    "ETHUSD": {"spread_points": 80, "commission_per_lot": 0.0, "min_profit_points": 30},
    "ETHUSDc": {"spread_points": 80, "commission_per_lot": 0.0, "min_profit_points": 30},
    "BTCUSD": {"spread_points": 500, "commission_per_lot": 0.0, "min_profit_points": 100},
    "BTCUSDc": {"spread_points": 500, "commission_per_lot": 0.0, "min_profit_points": 100},
    "UKOIL": {"spread_points": 20, "commission_per_lot": 0.0, "min_profit_points": 10},
}
V10_REVERSE_PROTECTION_PCT: float = 0.25
V10_GAP_PROTECTION_PCT: float = 0.002
V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT: float = 0.25
V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT: float = 0.001
V10_TRAILING_AGGRESSIVE_OFFSET_POINTS: dict[str, int] = {
    "EURUSD": 8,
    "EURUSDc": 8,
    "GBPUSD": 12,
    "GBPUSDc": 12,
    "USDJPY": 10,
    "USDJPYc": 10,
    "XAUUSD": 200,
    "XAUUSDc": 200,
    "US500": 15,
    "USTEC": 15,
    "US30": 20,
    "ETHUSD": 30,
    "ETHUSDc": 30,
    "BTCUSD": 50,
    "BTCUSDc": 50,
    "UKOIL": 15,
}
V10_COMPOUNDING_VOLUME_MULTIPLIER: float = 2.0
V10_COMPOUNDING_MIN_EQUITY: float = 5000.0
V10_SPREAD_MAX_POINTS_MULTIPLIER: float = 1.2
V10_MIN_BROKER_COVERAGE_POINTS: int = 1
V10_MAX_VOLUME_PER_CANDLE_RATIO: float = 0.03
V10_SPREAD_FILTER_BY_SYMBOL: dict[str, dict] = {
    "EURUSD": {"min_broker_coverage_points": 6, "multiplier": 2.0},
    "EURUSDc": {"min_broker_coverage_points": 6, "multiplier": 2.0},
    "GBPUSD": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "GBPUSDc": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "USDJPY": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "USDJPYc": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "XAUUSD": {"min_broker_coverage_points": 150, "multiplier": 1.5},
    "XAUUSDc": {"min_broker_coverage_points": 150, "multiplier": 1.5},
    "US500": {"min_broker_coverage_points": 10, "multiplier": 2.0},
    "USTEC": {"min_broker_coverage_points": 12, "multiplier": 2.0},
    "US30": {"min_broker_coverage_points": 12, "multiplier": 2.0},
    "ETHUSD": {"min_broker_coverage_points": 50, "multiplier": 2.0},
    "ETHUSDc": {"min_broker_coverage_points": 50, "multiplier": 2.0},
    "BTCUSD": {"min_broker_coverage_points": 300, "multiplier": 1.5},
    "BTCUSDc": {"min_broker_coverage_points": 300, "multiplier": 1.5},
    "UKOIL": {"min_broker_coverage_points": 10, "multiplier": 2.0},
}

# --- 6b-III. CONFIGURACIÓN V11 CRYPTO VOLATILITY (Heredado por V12) ---
V11_CRYPTO_VOLATILITY_ENABLED: bool = True
# Parámetros más agresivos para criptomonedas, que sobreescriben los de V10
V11_CRYPTO_PARAMS: dict[str, dict] = {
    "crypto": {
        "break_even_trigger_pct": 0.35,      # Breakeven más rápido (35% del TP)
        "reverse_protection_pct": 0.40,      # Cierre si retrocede 40% (más espacio)
        "trailing_activation_pct": 0.0025,   # Trailing se activa antes
        "trailing_offset_pct": 0.0012,       # Trailing más ajustado
    }
}

# --- 6b-IV. CONFIGURACIÓN V12 UNIVERSAL AGGRESSIVE ---
V12_UNIVERSAL_AGGRESSIVE_ENABLED: bool = True
V12_AGGRESSIVE_PARAMS: dict[str, dict] = {
    "gold": {
        "break_even_trigger_pct": 0.30,
        "reverse_protection_pct": 0.35,
        "trailing_activation_pct": 0.0020,
        "trailing_offset_pct": 0.0010,
    },
    "forex": {
        "break_even_trigger_pct": 0.40,
        "reverse_protection_pct": 0.45,
        "trailing_activation_pct": 0.0015,
        "trailing_offset_pct": 0.0008,
    },
    "index": {
        "break_even_trigger_pct": 0.35,
        "reverse_protection_pct": 0.40,
        "trailing_activation_pct": 0.0018,
        "trailing_offset_pct": 0.0012,
    },
    "commodity": {
        "break_even_trigger_pct": 0.35,
        "reverse_protection_pct": 0.40,
        "trailing_activation_pct": 0.0020,
        "trailing_offset_pct": 0.0015,
    }
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
    "ETHUSD": {
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 3.5,
        "risk_pct": 0.008,
    },
    "XAUUSD": {
        "sl_atr_mult": 0.7,
        "tp_atr_mult": 3.5,
        "risk_pct": 0.010,
    },
    "EURUSD": {
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.007,
    },
    "USDJPY": {
        "sl_atr_mult": 0.85,
        "tp_atr_mult": 2.2,
        "risk_pct": 0.007,
    },
    "US500": {
        "sl_atr_mult": 0.9,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.006,
    },
    "USTEC": {
        "sl_atr_mult": 0.95,
        "tp_atr_mult": 2.2,
        "risk_pct": 0.007,
    },
    "US30": {
        "sl_atr_mult": 0.9,
        "tp_atr_mult": 2.0,
        "risk_pct": 0.006,
    },
    "UKOIL": {
        "sl_atr_mult": 0.8,
        "tp_atr_mult": 2.4,
        "risk_pct": 0.008,
    },
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
