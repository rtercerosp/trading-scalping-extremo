import os
import sys
import MetaTrader5 as mt5
from datetime import datetime, timedelta, timezone
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv, find_dotenv
from data_provider.data_provider import DataProvider
from signal_generator.signal_generator import SignalGenerator
from platform_connector.platform_connector import PlatformConnector
from signal_generator.properties.signal_generator_properties import SmartMoneySignalProps
from portfolio.portfolio import Portfolio
from events.events import DataEvent

load_dotenv(find_dotenv())

if not mt5.initialize():
    print('Failed to initialize MT5')
    exit(1)

symbols_env = os.getenv("TRADING_SYMBOLS", "")
symbols = [s.strip() for s in symbols_env.split(',') if s.strip()]

connector = PlatformConnector(symbol_list=symbols, skip_warning=True)
portfolio = Portfolio(magic_number=20260728, max_positions_by_category={"crypto": 4, "forex": 6})

props = SmartMoneySignalProps(
    entry_timeframe="5min",
    trend_timeframe="15min",
    trend_fast_period=10,
    trend_slow_period=20,
    ema_fast_period=9,
    ema_slow_period=21,
    rsi_period=14,
    rsi_bull_threshold=52.0,
    rsi_bear_threshold=48.0,
    macd_fast=12,
    macd_slow=26,
    macd_signal=9,
    fvg_lookback=20,
    fib_lookback=30,
    atr_period=14,
    sl_atr_mult=1.2,
    tp_atr_mult=2.0,
    min_liquidity_gap_points=0.0,
    use_fibonacci=True,
    use_fvg=True,
    use_macd=True,
)

data_provider = DataProvider(
    events_queue=None,
    symbol_list=symbols,
    timeframe="5min",
    connector=connector,
    notification_service=None,
    stop_callback=None,
)

generator = SignalGenerator(
    events_queue=None,
    data_provider=data_provider,
    portfolio=portfolio,
    order_executor=None,
    signal_properties=props,
    connector=connector,
    trading_brain=None,
)

print("="*70)
print(f"MEDICIÓN DE SEÑALES SMART MONEY - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

for symbol in symbols:
    event = DataEvent(symbol=symbol, data=pd.Series())
    strategies = generator._get_strategies_for_asset(symbol)
    print(f"\n{symbol}:")
    print(f"  Estrategias: {[s.__class__.__name__ for s in strategies]}")
    for strategy in strategies:
        if hasattr(strategy, 'min_atr_points'):
            print(f"    {strategy.__class__.__name__}: ATR min = {strategy.min_atr_points} pts")
    try:
        signal = generator.generate_signal(event)
        if signal:
            print(f"  SEÑAL GENERADA: {signal.signal} SL={signal.sl} TP={signal.tp} TP1={signal.tp1} TP2={signal.tp2}")
        else:
            print(f"  Sin señal")
    except Exception as e:
        print(f"  Error: {e}")

connector.close()
mt5.shutdown()
