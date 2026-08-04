import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from ai.backtest_engine import BacktestEngine

engine = BacktestEngine(symbols=["BTCUSDc"], days_back=30, timeframe="5min")
results = engine.run()

for symbol, strategies in results.items():
    for strategy_name, data in strategies.items():
        if "Extreme" in strategy_name:
            print(f"{symbol} | {strategy_name}: trades={data['trades']}, signals={data['signals_generated']}")
