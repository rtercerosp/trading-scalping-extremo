import os
import sys
import MetaTrader5 as mt5
from datetime import datetime
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

if not mt5.initialize():
    print('Failed to initialize MT5')
    exit(1)

symbols_env = os.getenv("TRADING_SYMBOLS", "")
symbols = [s.strip() for s in symbols_env.split(',') if s.strip()]
if not symbols:
    print("No symbols configured in TRADING_SYMBOLS")
    mt5.shutdown()
    exit(1)

print("="*70)
print(f"MEDICIÓN DE SPREAD Y SEÑALES - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*70)

print("\nSpread actuales:")
print("-"*70)
for sym in symbols:
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info and tick:
        spread = tick.ask - tick.bid
        spread_pts = spread / info.point
        print(f"{sym}: ask={tick.ask} bid={tick.bid} spread={spread:.4f} ({spread_pts:.1f} pts)")

print("\n" + "="*70)
print("NOTA: Para medir señales, ejecutar trading_app.py con V3_SPREAD_AWARE")
print("="*70)

mt5.shutdown()
