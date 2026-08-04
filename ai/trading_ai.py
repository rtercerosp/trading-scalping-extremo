# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from typing import Dict, List, Optional
import pandas as pd
import json
import os
import logging
from utils.symbol_utils import get_asset_category, normalize_symbol

from .market_analyzer import CandlePatternAnalyzer
from .strategy_selector import StrategySelector, StrategyScore
from .learning_engine import LearningEngine

logger = logging.getLogger(__name__)


class TradingAI:
    def __init__(self, storage_path: str = "ai"):
        self.market_analyzer = CandlePatternAnalyzer()
        self.strategy_selector = StrategySelector(storage_path=f"{storage_path}/strategy_scores.json")
        self.learning_engine = LearningEngine(storage_path=f"{storage_path}/learning_params.json")
        self.analysis_cache: Dict[str, Dict] = {}
        self._load_backtest_scores(storage_path)

    def _load_backtest_scores(self, storage_path: str) -> None:
        backtest_path = os.path.join(storage_path, "backtest_results.json")
        if not os.path.exists(backtest_path):
            return
        try:
            with open(backtest_path, 'r') as f:
                backtest_data = json.load(f)
            for raw_symbol, strategies in backtest_data.items():
                symbol_key = normalize_symbol(raw_symbol)
                if symbol_key not in self.strategy_selector.scores:
                    self.strategy_selector.scores[symbol_key] = {}
                for strategy_name, score_data in strategies.items():
                    if strategy_name not in self.strategy_selector.scores[symbol_key]:
                        self.strategy_selector.scores[symbol_key][strategy_name] = StrategyScore.from_dict({
                            "strategy_name": score_data.get("strategy_name", strategy_name),
                            "score": score_data.get("score", 0.0),
                            "trades": score_data.get("trades", 0),
                            "wins": score_data.get("wins", 0),
                            "losses": score_data.get("losses", 0),
                            "profit": score_data.get("profit", 0.0),
                            "gross_profit": score_data.get("gross_profit", 0.0),
                            "gross_loss": score_data.get("gross_loss", 0.0),
                            "last_used": score_data.get("last_used"),
                        })
            for symbol_key, strategies in self.strategy_selector.scores.items():
                for strategy_name in list(strategies.keys()):
                    self.strategy_selector._check_probation(symbol_key, strategy_name)
            self.strategy_selector._save_scores()
        except Exception as e:
            logger.error("TRADING AI: Error inicializando backtest scores: %s", e, exc_info=True)

    def analyze_market(self, symbol: str, bars: pd.DataFrame) -> Dict:
        symbol_key = normalize_symbol(symbol)
        if bars.empty or len(bars) < 20:
            return {"valid": False, "reason": "insufficient_data"}

        behavior = self.market_analyzer.analyze_candle_behavior(bars)
        regime = self.market_analyzer.classify_market_regime(bars)

        result = {
            "valid": True,
            "symbol": symbol_key,
            "regime": regime,
            "behavior": behavior,
            "timestamp": pd.Timestamp.now().isoformat(),
        }
        self.analysis_cache[symbol_key] = result
        return result

    def select_strategy(self, symbol: str, available_strategies: List[str], market_regime: Optional[str] = None) -> str:
        normalized_symbol = normalize_symbol(symbol)
        if market_regime is None:
            cached = self.analysis_cache.get(normalized_symbol)
            market_regime = cached.get("regime", "neutral") if cached else "neutral"

        best = self.strategy_selector.get_best_strategy(normalized_symbol, available_strategies)
        if best is None:
            return available_strategies[0]

        asset_category = get_asset_category(normalized_symbol)
        if asset_category == "gold":
            for preferred_name in ("SignalTrendPullback", "SignalBreakout"):
                if preferred_name in available_strategies:
                    return preferred_name

        if market_regime in {"strong_bullish", "moderate_bullish"}:
            preferred = [s for s in available_strategies if "SmartMoney" in s or "Momentum" in s or "Pullback" in s]
            if preferred:
                return preferred[0]
        elif market_regime in {"strong_bearish", "moderate_bearish"}:
            preferred = [s for s in available_strategies if "Structure" in s or "Breakout" in s]
            if preferred:
                return preferred[0]
        elif market_regime == "range":
            preferred = [s for s in available_strategies if "EURUSD" in s or "TrendPullback" in s]
            if preferred:
                return preferred[0]

        return best

    def learn_from_trade(self, symbol: str, strategy_name: str, profit: float, sl_hit: bool, tp_hit: bool) -> Dict:
        self.strategy_selector.update_strategy_score(symbol, strategy_name, profit)
        params = self.learning_engine.update_params(symbol, profit, sl_hit, tp_hit)
        return params

    def get_adaptive_params(self, symbol: str) -> Dict:
        return self.learning_engine.get_adaptive_params(symbol)

    def get_market_analysis(self, symbol: str) -> Optional[Dict]:
        return self.analysis_cache.get(normalize_symbol(symbol))

    def get_strategy_stats(self, symbol: str) -> Dict:
        return self.strategy_selector.get_strategy_stats(symbol)
