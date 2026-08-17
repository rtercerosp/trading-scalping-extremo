#!/usr/bin/env python3
"""
Walk-forward validation for V10 Break-Even parameters.
Tests BE trigger %, trailing activation, and reverse protection against historical trades.
"""
import json
import os
from typing import Dict, List, Any

# Load historical trades from research database
research_db_path = os.path.join("research", "ml_database_trades.json")

if not os.path.exists(research_db_path):
    print(f"Research DB not found at {research_db_path}")
    exit(1)

with open(research_db_path, 'r') as f:
    all_trades = json.load(f)

# Filter to V13 trades (by strategy_version in parameter_set)
v13_trades = []
for t in all_trades:
    params = t.get("parameter_set", {})
    if params.get("strategy_version", "").startswith("V13"):
        v13_trades.append(t)

print(f"Total trades in research DB: {len(all_trades)}")
print(f"V13 trades: {len(v13_trades)}")

if len(v13_trades) < 10:
    print("Not enough V13 trades for validation, using all trades")
    v13_trades = all_trades

# Split into train/test (walk-forward: first 70% train, last 30% test)
split_idx = int(len(v13_trades) * 0.7)
train_trades = v13_trades[:split_idx]
test_trades = v13_trades[split_idx:]

print(f"Train: {len(train_trades)}, Test: {len(test_trades)}")

# Current V10 params from config
current_params = {
    "V10_BREAK_EVEN_TRIGGER_PCT": 0.10,
    "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT": 0.001,
    "V10_REVERSE_PROTECTION_PCT": 0.25,
    "V10_BREAK_EVEN_MIN_TRIGGER_POINTS": {
        "EURUSD": 8, "GBPUSD": 12, "USDJPY": 10, "XAUUSD": 200,
        "US500": 15, "USTEC": 15, "US30": 20, "ETHUSD": 15,
        "BTCUSD": 50, "UKOIL": 15
    }
}

# Test different parameter combinations
param_grid = {
    "be_trigger": [0.05, 0.08, 0.10, 0.12, 0.15],
    "trailing_activation": [0.0005, 0.001, 0.0015, 0.002, 0.003],
    "reverse_protection": [0.20, 0.25, 0.30, 0.35]
}

def simulate_be_exit(trade: Dict, be_trigger: float, trailing_act: float, rev_prot: float) -> Dict:
    """
    Simulate how a trade would have exited with given BE parameters.
    Uses mfe_points (max favorable excursion) and mae_points (max adverse excursion).
    """
    mfe = float(trade.get("mfe_points", 0.0) or 0.0)
    mae = float(trade.get("mae_points", 0.0) or 0.0)
    profit = float(trade.get("profit", 0.0) or 0.0)
    risk = float(trade.get("risk", 0.0) or 1.0)
    reward = float(trade.get("reward", 0.0) or 1.0)
    exit_reason = trade.get("exit_reason", "UNKNOWN")
    
    # Simplified BE simulation:
    # BE triggers when price moves in favor by be_trigger * (TP - Entry)
    tp_dist = reward
    be_trigger_dist = tp_dist * be_trigger
    
    # If MFE >= BE trigger, BE would have activated
    be_activated = mfe >= be_trigger_dist
    
    # Trailing activates after further move
    trailing_trigger_dist = tp_dist * trailing_act
    trailing_activated = mfe >= trailing_trigger_dist
    
    # Reverse protection: if price retraces rev_prot from BE level
    # Simplified: if BE activated but final profit < 0, reverse protection would close at loss
    reverse_triggered = be_activated and profit <= 0
    
    # Determine simulated exit
    if reverse_triggered:
        sim_exit = "REVERSE_PROTECTION"
        sim_profit = -risk * 0.5  # Approximate loss at reverse protection
    elif trailing_activated and profit > 0:
        sim_exit = "TRAILING_TP"
        sim_profit = profit  # Trailing would capture most profit
    elif be_activated and profit > 0:
        sim_exit = "BREAK_EVEN_TP"
        sim_profit = profit * 0.8  # BE + partial profit
    elif be_activated and profit <= 0:
        sim_exit = "BREAK_EVEN_SL"
        sim_profit = -risk * 0.1  # Small loss at BE
    else:
        # No BE activation - original exit
        sim_exit = exit_reason
        sim_profit = profit
    
    return {
        "sim_exit": sim_exit,
        "sim_profit": sim_profit,
        "be_activated": be_activated,
        "trailing_activated": trailing_activated,
        "reverse_triggered": reverse_triggered
    }

def evaluate_params(trades: List[Dict], be_trigger: float, trailing_act: float, rev_prot: float) -> Dict:
    """Evaluate a parameter set on a list of trades."""
    results = []
    for t in trades:
        sim = simulate_be_exit(t, be_trigger, trailing_act, rev_prot)
        results.append(sim)
    
    profits = [r["sim_profit"] for r in results]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]
    
    total_profit = sum(profits)
    win_rate = len(wins) / len(profits) if profits else 0
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999 if gross_profit > 0 else 0)
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
    
    exit_counts = {}
    for r in results:
        exit_counts[r["sim_exit"]] = exit_counts.get(r["sim_exit"], 0) + 1
    
    return {
        "total_profit": total_profit,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "trades": len(trades),
        "exit_counts": exit_counts
    }

# Test current params on train set
print("\n=== CURRENT PARAMS ON TRAIN ===")
current_eval = evaluate_params(train_trades, 
    current_params["V10_BREAK_EVEN_TRIGGER_PCT"],
    current_params["V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT"],
    current_params["V10_REVERSE_PROTECTION_PCT"]
)
print(f"Profit: {current_eval['total_profit']:.2f}, WR: {current_eval['win_rate']:.2%}, PF: {current_eval['profit_factor']:.2f}, Exp: {current_eval['expectancy']:.4f}")

# Grid search on train set
print("\n=== GRID SEARCH ON TRAIN ===")
best_score = -999
best_params = None

for be_t in param_grid["be_trigger"]:
    for trail_a in param_grid["trailing_activation"]:
        for rev_p in param_grid["reverse_protection"]:
            eval_result = evaluate_params(train_trades, be_t, trail_a, rev_p)
            score = eval_result["expectancy"] * eval_result["profit_factor"] * eval_result["win_rate"]
            if score > best_score:
                best_score = score
                best_params = {"be_trigger": be_t, "trailing_activation": trail_a, "reverse_protection": rev_p}
                print(f"NEW BEST: BE={be_t:.3f}, Trail={trail_a:.4f}, Rev={rev_p:.2f} -> Exp={eval_result['expectancy']:.4f}, PF={eval_result['profit_factor']:.2f}, WR={eval_result['win_rate']:.2%}")

print(f"\n=== BEST PARAMS ON TRAIN ===")
print(f"BE Trigger: {best_params['be_trigger']:.3f}")
print(f"Trailing Activation: {best_params['trailing_activation']:.4f}")
print(f"Reverse Protection: {best_params['reverse_protection']:.2f}")

# Validate best params on test set
print("\n=== BEST PARAMS ON TEST (OUT-OF-SAMPLE) ===")
test_eval = evaluate_params(test_trades, 
    best_params["be_trigger"],
    best_params["trailing_activation"],
    best_params["reverse_protection"]
)
print(f"Profit: {test_eval['total_profit']:.2f}, WR: {test_eval['win_rate']:.2%}, PF: {test_eval['profit_factor']:.2f}, Exp: {test_eval['expectancy']:.4f}")
print(f"Exit breakdown: {test_eval['exit_counts']}")

# Also test current params on test set
print("\n=== CURRENT PARAMS ON TEST ===")
current_test = evaluate_params(test_trades,
    current_params["V10_BREAK_EVEN_TRIGGER_PCT"],
    current_params["V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT"],
    current_params["V10_REVERSE_PROTECTION_PCT"]
)
print(f"Profit: {current_test['total_profit']:.2f}, WR: {current_test['win_rate']:.2%}, PF: {current_test['profit_factor']:.2f}, Exp: {current_test['expectancy']:.4f}")

# Per-symbol analysis
print("\n=== PER-SYMBOL ANALYSIS (TEST SET) ===")
symbols = set(t.get("symbol", "") for t in test_trades)
for sym in sorted(symbols):
    sym_trades = [t for t in test_trades if t.get("symbol") == sym]
    if len(sym_trades) < 5:
        continue
    sym_eval = evaluate_params(sym_trades,
        best_params["be_trigger"],
        best_params["trailing_activation"],
        best_params["reverse_protection"]
    )
    print(f"{sym}: Trades={sym_eval['trades']}, Exp={sym_eval['expectancy']:.4f}, PF={sym_eval['profit_factor']:.2f}, WR={sym_eval['win_rate']:.2%}")

print("\n=== RECOMMENDATION ===")
if test_eval["expectancy"] > current_test["expectancy"]:
    print(f"Optimized params IMPROVE expectancy: {current_test['expectancy']:.4f} -> {test_eval['expectancy']:.4f}")
    print("Consider updating config.py with:")
    print(f"  V10_BREAK_EVEN_TRIGGER_PCT = {best_params['be_trigger']:.3f}")
    print(f"  V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT = {best_params['trailing_activation']:.4f}")
    print(f"  V10_REVERSE_PROTECTION_PCT = {best_params['reverse_protection']:.2f}")
else:
    print(f"Current params are better or equal: {current_test['expectancy']:.4f} vs {test_eval['expectancy']:.4f}")
    print("Keep current config values.")