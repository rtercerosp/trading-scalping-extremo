from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Any

from research.research_database import ResearchDatabase


@dataclass
class ExitModelStats:
    name: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    profit: float = 0.0
    mfe_mean: float = 0.0
    mae_mean: float = 0.0
    avg_duration_seconds: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    avg_r: float = 0.0
    max_drawdown: float = 0.0
    score: float = 0.0


class ExitModelComparator:
    def __init__(self, db: ResearchDatabase) -> None:
        self.db = db

    def evaluate(self, trades: list[dict[str, Any]]) -> dict[str, ExitModelStats]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for t in trades:
            grouped.setdefault(t.get("model_used", "default"), []).append(t)

        rankings: dict[str, ExitModelStats] = {}
        for model, items in grouped.items():
            stats = self._stats_for_model(model, items)
            rankings[model] = stats

        ranked = sorted(rankings.items(), key=lambda kv: kv[1].score, reverse=True)
        ranked_dict = {k: {
            "trades": v.trades,
            "wins": v.wins,
            "losses": v.losses,
            "profit": v.profit,
            "mfe_mean": v.mfe_mean,
            "mae_mean": v.mae_mean,
            "avg_duration_seconds": v.avg_duration_seconds,
            "expectancy": v.expectancy,
            "profit_factor": v.profit_factor,
            "win_rate": v.win_rate,
            "avg_r": v.avg_r,
            "max_drawdown": v.max_drawdown,
            "score": v.score,
        } for k, v in ranked}

        self.db.update_exit_model_rankings({"ranked_models": ranked_dict, "count": len(ranked_dict)})
        return rankings

    def _stats_for_model(self, name: str, trades: list[dict[str, Any]]) -> ExitModelStats:
        wins = [t for t in trades if t.get("win")]
        losses = [t for t in trades if not t.get("win")]
        profit = sum(float(t.get("profit", 0.0) or 0.0) for t in trades)
        mfe_mean = mean([float(t.get("mfe_points", 0.0) or 0.0) for t in trades]) if trades else 0.0
        mae_mean = mean([float(t.get("mae_points", 0.0) or 0.0) for t in trades]) if trades else 0.0
        avg_dur = mean([float(t.get("trade_duration_seconds", 0) or 0) for t in trades]) if trades else 0.0

        gross_profit = sum(float(t.get("profit", 0.0) or 0.0) for t in wins) if wins else 0.0
        gross_loss = abs(sum(float(t.get("profit", 0.0) or 0.0) for t in losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        win_rate = len(wins) / len(trades) if trades else 0.0
        avg_win = mean([float(t.get("profit", 0.0) or 0.0) for t in wins]) if wins else 0.0
        avg_loss = abs(mean([float(t.get("profit", 0.0) or 0.0) for t in losses])) if losses else 0.0
        avg_r = (avg_win / avg_loss) if avg_loss > 0 else (999.0 if avg_win > 0 else 0.0)

        running = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in trades:
            running += float(t.get("profit", 0.0) or 0.0)
            peak = max(peak, running)
            max_dd = max(max_dd, peak - running)

        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        score = self._score(profit_factor, win_rate, expectancy, max_dd, len(trades))

        return ExitModelStats(
            name=name,
            trades=len(trades),
            wins=len(wins),
            losses=len(losses),
            profit=profit,
            mfe_mean=mfe_mean,
            mae_mean=mae_mean,
            avg_duration_seconds=avg_dur,
            expectancy=expectancy,
            profit_factor=profit_factor,
            win_rate=win_rate,
            avg_r=avg_r,
            max_drawdown=max_dd,
            score=score,
        )

    def _score(self, profit_factor: float, win_rate: float, expectancy: float, max_dd: float, trades: int) -> float:
        if trades <= 0:
            return 0.0
        trade_confidence = min(1.0, trades / 50.0)
        return float(trade_confidence * (
            0.35 * max(0.0, min(1.0, (profit_factor - 1) / 4.0)) +
            0.25 * win_rate +
            0.25 * max(0.0, min(1.0, (expectancy + 10) / 20.0)) +
            0.15 * max(0.0, min(1.0, (10000 - max_dd) / 10000))
        ))
