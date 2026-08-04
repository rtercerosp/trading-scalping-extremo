from typing import Dict

from utils.symbol_utils import normalize_symbol


class PerformanceTracker:
    def __init__(self) -> None:
        self.asset_performance: Dict[str, Dict] = {}
        self.strategy_performance: Dict[str, Dict[str, Dict]] = {}

    def update_asset_performance(self, symbol: str, profit: float) -> None:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.asset_performance:
            self.asset_performance[symbol_key] = {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "total_profit": 0.0,
                "avg_profit": 0.0,
                "win_rate": 0.0,
            }

        perf = self.asset_performance[symbol_key]
        perf["total_trades"] += 1
        perf["total_profit"] += profit
        perf["avg_profit"] = perf["total_profit"] / perf["total_trades"]

        if profit > 0:
            perf["winning_trades"] += 1
        else:
            perf["losing_trades"] += 1

        perf["win_rate"] = perf["winning_trades"] / perf["total_trades"] if perf["total_trades"] > 0 else 0.0

    def update_strategy_performance(self, symbol: str, strategy: str, profit: float) -> None:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.strategy_performance:
            self.strategy_performance[symbol_key] = {}
        if strategy not in self.strategy_performance[symbol_key]:
            self.strategy_performance[symbol_key][strategy] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0.0,
                "win_rate": 0.0,
            }
        rec = self.strategy_performance[symbol_key][strategy]
        rec["trades"] += 1
        rec["profit"] += profit
        if profit > 0:
            rec["wins"] += 1
        else:
            rec["losses"] += 1
        rec["win_rate"] = rec["wins"] / rec["trades"] if rec["trades"] > 0 else 0.0

    def get_asset_performance(self, symbol: str) -> Dict:
        return self.asset_performance.get(normalize_symbol(symbol), {})

    def get_strategy_performance(self, symbol: str, strategy: str) -> Dict:
        symbol_key = normalize_symbol(symbol)
        return self.strategy_performance.get(symbol_key, {}).get(strategy, {})
