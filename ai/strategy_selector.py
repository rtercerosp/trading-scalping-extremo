# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import json
import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from utils.symbol_utils import normalize_symbol
import config

logger = logging.getLogger(__name__)

class StrategyScore:
    def __init__(self, strategy_name: str, score: float = 0.0, trades: int = 0, wins: int = 0, losses: int = 0, profit: float = 0.0, gross_profit: float = 0.0, gross_loss: float = 0.0, probation_until: Optional[str] = None):
        self.strategy_name = strategy_name
        self.score = score
        self.trades = trades
        self.wins = wins
        self.losses = losses
        self.profit = profit
        self.gross_profit = gross_profit
        self.gross_loss = gross_loss
        self.probation_until = probation_until
        self.last_used = datetime.now().isoformat()

    def is_in_probation(self) -> bool:
        if not self.probation_until:
            return False
        try:
            probation_deadline = datetime.fromisoformat(self.probation_until)
            return datetime.now() < probation_deadline
        except (ValueError, TypeError):
            return False

    def update(self, profit: float) -> None:
        self.trades += 1
        self.profit += profit
        if profit > 0:
            self.wins += 1
            self.gross_profit += profit
        else:
            self.losses += 1
            self.gross_loss += abs(profit)
        self.last_used = datetime.now().isoformat()
        win_rate = self.wins / self.trades if self.trades > 0 else 0
        profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else float('inf') if self.gross_profit > 0 else 0.0
        expectancy = self.profit / self.trades if self.trades > 0 else 0.0
        expectancy_score = max(min(expectancy * 2.0, 20.0), -20.0)
        self.score = (win_rate * 50) + (min(profit_factor, 4.0) * 12.5) + (min(self.trades / 20.0, 5.0) * 5) + expectancy_score

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "score": self.score,
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "profit": self.profit,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "last_used": self.last_used,
            "probation_until": self.probation_until,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyScore":
        return cls(
            strategy_name=data["strategy_name"],
            score=data.get("score", 0.0),
            trades=data.get("trades", 0),
            wins=data.get("wins", 0),
            losses=data.get("losses", 0),
            profit=data.get("profit", 0.0),
            gross_profit=data.get("gross_profit", 0.0),
            gross_loss=data.get("gross_loss", 0.0),
            probation_until=data.get("probation_until"),
        )


class StrategySelector:
    def __init__(self, storage_path: str = "ai/strategy_scores.json"):
        self.storage_path = storage_path
        self.scores: Dict[str, Dict[str, StrategyScore]] = {}
        self._load_scores()

    def _load_scores(self) -> None:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding="utf-8") as f:
                    data = json.load(f)
                    for symbol, strategies in data.items():
                        self.scores[symbol] = {}
                        for strategy_name, score_data in strategies.items():
                            self.scores[symbol][strategy_name] = StrategyScore.from_dict(score_data)
            except Exception as e:
                logger.error("STRATEGY SELECTOR: Error cargando scores desde %s: %s", self.storage_path, e, exc_info=True)

    def _save_scores(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
            data = {}
            for symbol, strategies in self.scores.items():
                data[symbol] = {name: score.to_dict() for name, score in strategies.items()}
            with open(self.storage_path, 'w', encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("STRATEGY SELECTOR: Error guardando scores en %s: %s", self.storage_path, e, exc_info=True)

    def _check_probation(self, symbol_key: str, strategy_name: str) -> None:
        if symbol_key not in self.scores or strategy_name not in self.scores[symbol_key]:
            return
        score = self.scores[symbol_key][strategy_name]
        if score.trades >= config.PROBATION_MIN_TRADES and score.gross_loss > 0 and (score.gross_profit / score.gross_loss) < config.PROBATION_PROFIT_FACTOR_THRESHOLD:
            score.probation_until = (datetime.now() + config.PROBATION_DURATION).isoformat()
            self._save_scores()

    def get_best_strategy(self, symbol: str, available_strategies: List[str]) -> Optional[str]:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.scores:
            self.scores[symbol_key] = {}

        best_strategy = None
        best_score = -float('inf')

        for strategy_name in available_strategies:
            if strategy_name not in self.scores[symbol_key]:
                self.scores[symbol_key][strategy_name] = StrategyScore(strategy_name=strategy_name)
            score = self.scores[symbol_key][strategy_name]
            if score.is_in_probation():
                continue
            if score.score > best_score:
                best_score = score.score
                best_strategy = strategy_name

        return best_strategy

    def update_strategy_score(self, symbol: str, strategy_name: str, profit: float) -> None:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.scores:
            self.scores[symbol_key] = {}
        if strategy_name not in self.scores[symbol_key]:
            self.scores[symbol_key][strategy_name] = StrategyScore(strategy_name=strategy_name)
        self.scores[symbol_key][strategy_name].update(profit)
        self._check_probation(symbol_key, strategy_name)
        self._save_scores()

    def get_strategy_stats(self, symbol: str) -> Dict[str, Dict]:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.scores:
            return {}
        return {name: score.to_dict() for name, score in self.scores[symbol_key].items()}

    def get_probation_status(self, symbol: str, strategy_name: str) -> Dict:
        symbol_key = normalize_symbol(symbol)
        if symbol_key not in self.scores or strategy_name not in self.scores[symbol_key]:
            return {"in_probation": False, "probation_until": None}
        score = self.scores[symbol_key][strategy_name]
        return {
            "in_probation": score.is_in_probation(),
            "probation_until": score.probation_until,
            "score": score.score,
            "trades": score.trades,
            "profit_factor": score.gross_profit / score.gross_loss if score.gross_loss > 0 else float('inf') if score.gross_profit > 0 else 0.0,
        }
