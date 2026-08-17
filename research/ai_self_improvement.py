from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any

from research.research_database import ResearchDatabase


@dataclass
class AIRecommendations:
    best_symbols: list[str] = None  # type: ignore
    best_sessions: list[str] = None  # type: ignore
    best_volatility_conditions: list[str] = None  # type: ignore
    best_trend_conditions: list[str] = None  # type: ignore
    best_stop_placement: dict[str, Any] = None  # type: ignore
    best_profit_extraction: dict[str, Any] = None  # type: ignore
    best_trailing_methodology: dict[str, Any] = None  # type: ignore
    best_portfolio_allocation: dict[str, Any] = None  # type: ignore
    worst_recurring_mistakes: list[str] = None  # type: ignore
    highest_probability_structures: list[str] = None  # type: ignore
    ranked_recommendations: list[str] = None  # type: ignore


class AISelfImprovement:
    def __init__(self, db: ResearchDatabase) -> None:
        self.db = db

    def analyze(self, trades: list[dict[str, Any]]) -> AIRecommendations:
        if not trades:
            return AIRecommendations()

        wins = [t for t in trades if t.get("win")]
        losses = [t for t in trades if not t.get("win")]

        best_symbols = self._rank_by(trades, lambda t: t.get("symbol"), float(t.get("profit", 0.0) or 0.0))
        best_sessions = self._rank_by(trades, lambda t: t.get("session", "unknown"), float(t.get("profit", 0.0) or 0.0))
        best_volatility = self._rank_by(trades, lambda t: str(t.get("regime", "unknown")), float(t.get("profit", 0.0) or 0.0))
        best_trend = self._rank_by(trades, lambda t: str(t.get("trend_strength", 0.0)), float(t.get("profit", 0.0) or 0.0))

        stop_placements: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            stop_placements[str(t.get("exit_reason", ""))].append(float(t.get("profit", 0.0) or 0.0))
        best_stop_placement = {k: {"avg_profit": mean(v), "count": len(v)} for k, v in stop_placements.items()}

        profit_extraction: dict[str, list[float]] = defaultdict(list)
        trailing_scores: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            profit_extraction[t.get("model_used", "default")].append(float(t.get("profit", 0.0) or 0.0))
            trailing_scores[str(t.get("exit_reason", ""))].append(float(t.get("mfe_points", 0.0) or 0.0))
        best_profit_extraction = {k: {"avg_profit": mean(v), "count": len(v)} for k, v in profit_extraction.items()}
        best_trailing_methodology = {k: {"avg_mfe": mean(v), "count": len(v)} for k, v in trailing_scores.items()}

        allocation: dict[str, float] = {}
        for t in trades:
            allocation[t.get("symbol", "unknown")] = allocation.get(t.get("symbol", "unknown"), 0.0) + float(t.get("profit", 0.0) or 0.0)
        best_portfolio_allocation = allocation

        worst_mistakes = sorted(
            [t.get("exit_reason", "unknown") for t in losses],
            key=lambda x: losses.count([t for t in losses if t.get("exit_reason") == x][0]) if any(t.get("exit_reason") == x for t in losses) else 0,
            reverse=False,
        )
        unique_mistakes = []
        for x in worst_mistakes:
            if x not in unique_mistakes:
                unique_mistakes.append(x)

        structures = []
        for t in trades:
            if t.get("win") and float(t.get("mfe_points", 0.0) or 0.0) > 0:
                structures.append(t.get("regime", "unknown"))
        structure_counts = {s: structures.count(s) for s in set(structures)}
        highest_probability_structures = [k for k, _ in sorted(structure_counts.items(), key=lambda kv: kv[1], reverse=True)][:10]

        ranked_recommendations = [
            f"Top symbol: {best_symbols[0]}" if best_symbols else "",
            f"Top session: {best_sessions[0]}" if best_sessions else "",
            f"Best exit model: {max(best_profit_extraction.items(), key=lambda kv: kv[1]['avg_profit'])[0]}" if best_profit_extraction else "",
            f"Worst mistake pattern: {unique_mistakes[0]}" if unique_mistakes else "",
            f"Highest-probability structure: {highest_probability_structures[0]}" if highest_probability_structures else "",
        ]
        ranked_recommendations = [r for r in ranked_recommendations if r]

        recommendations = AIRecommendations(
            best_symbols=best_symbols[:10],
            best_sessions=best_sessions[:10],
            best_volatility_conditions=best_volatility[:10],
            best_trend_conditions=best_trend[:10],
            best_stop_placement=best_stop_placement,
            best_profit_extraction=best_profit_extraction,
            best_trailing_methodology=best_trailing_methodology,
            best_portfolio_allocation=best_portfolio_allocation,
            worst_recurring_mistakes=unique_mistakes[:10],
            highest_probability_structures=highest_probability_structures,
            ranked_recommendations=ranked_recommendations,
        )
        self.db.update_ai_recommendations({
            "best_symbols": recommendations.best_symbols,
            "best_sessions": recommendations.best_sessions,
            "best_volatility_conditions": recommendations.best_volatility_conditions,
            "best_trend_conditions": recommendations.best_trend_conditions,
            "best_stop_placement": recommendations.best_stop_placement,
            "best_profit_extraction": recommendations.best_profit_extraction,
            "best_trailing_methodology": recommendations.best_trailing_methodology,
            "best_portfolio_allocation": recommendations.best_portfolio_allocation,
            "worst_recurring_mistakes": recommendations.worst_recurring_mistakes,
            "highest_probability_structures": recommendations.highest_probability_structures,
            "ranked_recommendations": recommendations.ranked_recommendations,
        })
        return recommendations

    def _rank_by(self, trades: list[dict[str, Any]], key_fn, value_fn) -> list[str]:
        grouped: dict[str, list[float]] = {}
        for t in trades:
            k = key_fn(t)
            grouped.setdefault(str(k), []).append(value_fn(t))
        ranked = sorted(grouped.items(), key=lambda kv: mean(kv[1]) if kv[1] else -9999.0, reverse=True)
        return [k for k, _ in ranked]
