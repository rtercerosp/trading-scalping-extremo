#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-cargador de conocimiento V6.
Ejecuta backtest historico sobre datos reales de MT5 y alimenta la IA con:
  - Scores por estrategia por activo
  - Parametros adaptativos iniciales
  - Reglas expertas de correlacion inter-mercado y eventos macro
Uso:
    python run_preload.py
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta

# Configurar path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from ai.backtest_engine import BacktestEngine
from utils.utils import Utils


def run_preload() -> None:
    print("=" * 70)
    print(f"{Utils.dateprint()} - PRELOAD: Iniciando pre-carga de conocimiento V6")
    print(f"{Utils.dateprint()} - PRELOAD: Activos: {', '.join(config.DEFAULT_SYMBOLS)}")
    print(f"{Utils.dateprint()} - PRELOAD: Dias historicos: {config.BACKTEST_DAYS}, Timeframe: {config.BACKTEST_TIMEFRAME}")
    print("=" * 70)

    engine = BacktestEngine(symbols=config.DEFAULT_SYMBOLS, days_back=config.BACKTEST_DAYS, timeframe=config.BACKTEST_TIMEFRAME)
    start_time = time.time()

    results = engine.run()

    elapsed = time.time() - start_time
    print(f"\n{Utils.dateprint()} - PRELOAD: Backtest completado en {elapsed:.2f} segundos")

    if not results:
        print(f"{Utils.dateprint()} - PRELOAD: No se obtuvieron resultados del backtest")
        return

    strategy_scores_path = os.path.join("ai", "strategy_scores.json")
    try:
        if os.path.exists(strategy_scores_path):
            with open(strategy_scores_path, 'r') as f:
                existing_scores = json.load(f)
        else:
            existing_scores = {}

        updated = False
        for symbol, strategies in results.items():
            if symbol not in existing_scores:
                existing_scores[symbol] = {}

            for strategy_name, score_data in strategies.items():
                existing_score = existing_scores[symbol].get(strategy_name, {})

                merged = dict(existing_score)
                merged.update(score_data)
                merged["last_used"] = datetime.now().isoformat()

                existing_scores[symbol][strategy_name] = merged
                updated = True

                print(f"{Utils.dateprint()} - PRELOAD: {symbol} | {strategy_name}: "
                      f"score={score_data.get('score', 0):.2f}, "
                      f"trades={score_data.get('trades', 0)}, "
                      f"wr={score_data.get('win_rate', 0):.2%}, "
                      f"pf={score_data.get('profit_factor', 0):.2f}")

        if updated:
            os.makedirs(os.path.dirname(strategy_scores_path), exist_ok=True)
            with open(strategy_scores_path, 'w') as f:
                json.dump(existing_scores, f, indent=2)
            print(f"\n{Utils.dateprint()} - PRELOAD: strategy_scores.json actualizado con resultados de backtest")
    except Exception as e:
        print(f"{Utils.dateprint()} - PRELOAD: Error actualizando strategy_scores.json: {e}")

    engine.save_results(path=os.path.join("ai", "backtest_results.json"))

    best_strategies = engine.get_best_strategies_by_symbol(top_n=3)
    print(f"\n{Utils.dateprint()} - PRELOAD: Mejores estrategias por activo (top 3):")
    for symbol, strats in best_strategies.items():
        print(f"{Utils.dateprint()} - PRELOAD:   {symbol}: {', '.join(strats)}")

    print("\n" + "=" * 70)
    print(f"{Utils.dateprint()} - PRELOAD: Pre-carga completada")
    print("=" * 70)


if __name__ == "__main__":
    run_preload()
