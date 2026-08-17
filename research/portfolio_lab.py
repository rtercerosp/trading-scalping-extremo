from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Any

from research.research_database import ResearchDatabase


@dataclass
class PortfolioLabState:
    open_positions: int = 0
    capital: float = 0.0
    open_risk: float = 0.0
    closed_risk: float = 0.0
    exposure_by_symbol: dict[str, float] = field(default_factory=dict)
    return_by_symbol: dict[str, float] = field(default_factory=dict)
    return_by_strategy: dict[str, float] = field(default_factory=dict)
    return_by_session: dict[str, float] = field(default_factory=dict)
    heat: float = 0.0
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    capital_allocation: dict[str, float] = field(default_factory=dict)
    risk_budget_used: float = 0.0
    efficiency_score: float = 0.0
    notes: str = ""


class PortfolioLab:
    def __init__(self, db: ResearchDatabase) -> None:
        self.db = db

    def update_state(self, state: PortfolioLabState) -> None:
        payload = {
            "portfolio_lab": {
                "open_positions": state.open_positions,
                "capital": state.capital,
                "open_risk": state.open_risk,
                "closed_risk": state.closed_risk,
                "exposure_by_symbol": state.exposure_by_symbol,
                "return_by_symbol": state.return_by_symbol,
                "return_by_strategy": state.return_by_strategy,
                "return_by_session": state.return_by_session,
                "heat": state.heat,
                "correlation_matrix": state.correlation_matrix,
                "capital_allocation": state.capital_allocation,
                "risk_budget_used": state.risk_budget_used,
                "efficiency_score": state.efficiency_score,
                "notes": state.notes,
            }
        }
        self.db.update_summary(payload)

    def compute_heat(self, exposure: dict[str, float], capital: float) -> float:
        if capital <= 0:
            return 0.0
        total = sum(abs(v) for v in exposure.values())
        return float(total / capital)

    def compute_correlation_matrix(self, returns_by_symbol: dict[str, list[float]]) -> dict[str, dict[str, float]]:
        symbols = list(returns_by_symbol.keys())
        matrix: dict[str, dict[str, float]] = {}
        for s1 in symbols:
            matrix[s1] = {}
            r1 = returns_by_symbol.get(s1, [])
            for s2 in symbols:
                r2 = returns_by_symbol.get(s2, [])
                if s1 == s2:
                    matrix[s1][s2] = 1.0
                else:
                    matrix[s1][s2] = self._pearson(r1, r2)
        return matrix

    def compute_capital_allocation(self, returns_by_symbol: dict[str, float], total_capital: float) -> dict[str, float]:
        if total_capital <= 0:
            return {k: 0.0 for k in returns_by_symbol}
        total_return = sum(abs(v) for v in returns_by_symbol.values())
        if total_return <= 0:
            equal = 1.0 / max(1, len(returns_by_symbol))
            return {k: equal for k in returns_by_symbol}
        return {k: abs(v) / total_return for k, v in returns_by_symbol.items()}

    def _pearson(self, x: list[float], y: list[float]) -> float:
        n = min(len(x), len(y))
        if n < 2:
            return 0.0
        x = x[-n:]
        y = y[-n:]
        mx = mean(x)
        my = mean(y)
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        den = math.sqrt(sum((xi - mx) ** 2 for xi in x)) * math.sqrt(sum((yi - my) ** 2 for yi in y))
        if den == 0:
            return 0.0
        return num / den
