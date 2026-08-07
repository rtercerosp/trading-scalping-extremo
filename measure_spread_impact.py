import MetaTrader5 as mt5
from datetime import datetime

if not mt5.initialize():
    print('Failed to initialize MT5')
    exit()

symbols = ['XAUUSDc', 'EURUSDc', 'USDJPYc', 'US500', 'USTEC', 'BTCUSDc', 'US30', 'ETHUSDc', 'UKOIL']
now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print('='*70)
print(f'MEDICIÓN DE SPREAD - {now}')
print('='*70)
print(f'{"Activo":<12} {"Ask":>12} {"Bid":>12} {"Spread":>10} {"Puntos":>10} {"bps":>8}')
print('-'*70)
for sym in symbols:
    info = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym)
    if info and tick:
        spread = tick.ask - tick.bid
        spread_pts = spread / info.point
        spread_bps = (spread / tick.ask) * 10000
        print(f'{sym:<12} {tick.ask:>12.4f} {tick.bid:>12.4f} {spread:>10.4f} {spread_pts:>10.1f} {spread_bps:>8.2f}')
    else:
        print(f'{sym:<12} {"N/A":>12}')

print('='*70)
print('Impacto en SL/TP para V3_SPREAD_AWARE:')
print('-'*70)

# Impacto para BTC
btc_spread_pts = 1000
btc_atr_min = 200
btc_sl = 1.2 * btc_atr_min + btc_spread_pts * 1.5 + 20
btc_tp = 1.5 * btc_atr_min + btc_spread_pts * 1.5 * 1.2 + 20
print(f'BTCUSDc: spread={btc_spread_pts} pts, ATR min={btc_atr_min} pts')
print(f'  SL calculado: {btc_sl:.1f} pts (1.2*ATR + spread buffer)')
print(f'  TP calculado: {btc_tp:.1f} pts (1.5*ATR + spread buffer)')
print(f'  Ratio SL/TP: {btc_sl/btc_tp:.2f}')
print()

# Impacto para ETH
eth_spread_pts = 100
eth_atr_min = 100
eth_sl = 1.2 * eth_atr_min + eth_spread_pts * 1.5 + 20
eth_tp = 1.5 * eth_atr_min + eth_spread_pts * 1.5 * 1.2 + 20
print(f'ETHUSDc: spread={eth_spread_pts} pts, ATR min={eth_atr_min} pts')
print(f'  SL calculado: {eth_sl:.1f} pts (1.2*ATR + spread buffer)')
print(f'  TP calculado: {eth_tp:.1f} pts (1.5*ATR + spread buffer)')
print(f'  Ratio SL/TP: {eth_sl/eth_tp:.2f}')
print()

# Impacto para EURUSD
eur_spread_pts = 48
eur_atr_min = 50
eur_sl = 1.2 * eur_atr_min + eur_spread_pts * 1.5 + 20
eur_tp = 0.8 * eur_atr_min + eur_spread_pts * 1.5 * 1.2 + 20
print(f'EURUSDc: spread={eur_spread_pts} pts, ATR min={eur_atr_min} pts')
print(f'  SL calculado: {eur_sl:.1f} pts (1.2*ATR + spread buffer)')
print(f'  TP calculado: {eur_tp:.1f} pts (0.8*ATR + spread buffer)')
print(f'  Ratio SL/TP: {eur_sl/eur_tp:.2f}')
print()

# Impacto para XAUUSD
xau_spread_pts = 260
xau_atr_min = 100
xau_sl = 1.0 * xau_atr_min + xau_spread_pts * 1.5 + 20
xau_tp = 0.9 * xau_atr_min + xau_spread_pts * 1.5 * 1.2 + 20
print(f'XAUUSDc: spread={xau_spread_pts} pts, ATR min={xau_atr_min} pts')
print(f'  SL calculado: {xau_sl:.1f} pts (1.0*ATR + spread buffer)')
print(f'  TP calculado: {xau_tp:.1f} pts (0.9*ATR + spread buffer)')
print(f'  Ratio SL/TP: {xau_sl/xau_tp:.2f}')
print()

print('='*70)
print('NOTA: Estos valores son estimaciones. Ejecutar el bot para medir en tiempo real.')
print('='*70)

mt5.shutdown()
