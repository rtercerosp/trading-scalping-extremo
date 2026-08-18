from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from statistics import mean, median
from typing import Any

from research.research_database import ResearchDatabase


@dataclass
class ScientificMetrics:
    profit_factor: float = 0.0
    win_rate: float = 0.0
    expectancy: float = 0.0
    recovery_factor: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    avg_r: float = 0.0
    drawdown: float = 0.0
    risk_of_ruin: float = 0.0
    max_consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    avg_holding_time_seconds: float = 0.0
    capital_growth_rate: float = 0.0
    monte_carlo_confidence: float = 0.0
    parameter_sensitivity: dict[str, float] = None  # type: ignore
    strategy_stability: float = 0.0
    out_of_sample_performance: float = 0.0
    walk_forward_performance: float = 0.0


class AdvancedMetricsEngine:
    def __init__(self, db: ResearchDatabase) -> None:
        self.db = db

    def compute(self, trades: list[dict[str, Any]]) -> ScientificMetrics:
        if not trades:
            return ScientificMetrics()

        profits = [float(t.get("profit", 0.0) or 0.0) for t in trades]
        durations = [float(t.get("trade_duration_seconds", 0) or 0) for t in trades]
        r_multiples = [float(t.get("reward", 0.0) or 0.0) / max(float(t.get("risk", 0.0) or 0.0), 1e-9) for t in trades]

        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0

        win_rate = len(wins) / len(profits) if profits else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0.0)
        avg_win = mean(wins) if wins else 0.0
        avg_loss = abs(mean(losses)) if losses else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        avg_r = mean([r for r in r_multiples if math.isfinite(r)]) if r_multiples else 0.0

        equity = []
        run = 0.0
        peak = 0.0
        max_dd = 0.0
        consecutive_losses = 0
        consecutive_wins = 0
        max_consecutive_losses = 0
        max_consecutive_wins = 0
        for p in profits:
            run += p
            equity.append(run)
            peak = max(peak, run)
            max_dd = max(max_dd, peak - run)
            if p <= 0:
                consecutive_losses += 1
                consecutive_wins = 0
                max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            else:
                consecutive_wins += 1
                consecutive_losses = 0
                max_consecutive_wins = max(max_consecutive_wins, consecutive_wins)

        recovery_factor = run / max_dd if max_dd > 0 else (999.0 if run > 0 else 0.0)

        returns = profits
        mean_r = mean(returns) if returns else 0.0
        std_r = stdev(returns) if len(returns) > 1 else 0.0
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0.0

        downside = [r for r in returns if r < 0]
        std_down = stdev(downside) if len(downside) > 1 else 0.0
        sortino = (mean_r / std_down * math.sqrt(252)) if std_down > 0 else 0.0

        calmar = (run / max_dd) if max_dd > 0 else 0.0

        risk_of_ruin = self._risk_of_ruin(win_rate, avg_win, avg_loss)
        avg_hold = mean(durations) if durations else 0.0
        growth = self._growth_rate(equity)
        mc_conf = self._monte_carlo_confidence(profits)
        sensitivity = self._parameter_sensitivity(trades)
        stability = self._strategy_stability(trades)
        oos = self._out_of_sample(trades)
        wf = self._walk_forward(trades)

        metrics = ScientificMetrics(
            profit_factor=profit_factor,
            win_rate=win_rate,
            expectancy=expectancy,
            recovery_factor=recovery_factor,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            avg_r=avg_r,
            drawdown=max_dd,
            risk_of_ruin=risk_of_ruin,
            max_consecutive_losses=max_consecutive_losses,
            max_consecutive_wins=max_consecutive_wins,
            avg_holding_time_seconds=avg_hold,
            capital_growth_rate=growth,
            monte_carlo_confidence=mc_conf,
            parameter_sensitivity=sensitivity,
            strategy_stability=stability,
            out_of_sample_performance=oos,
            walk_forward_performance=wf,
        )

        self.db.update_summary({"advanced_metrics": self._to_dict(metrics)})
        return metrics

    def generate_report(self, trades: list[dict[str, Any]], metrics: ScientificMetrics, exit_rankings: dict[str, Any], portfolio_state: dict[str, Any]) -> str:
        lines = [
            "# RESEARCH REPORT",
            f"- trades: {len(trades)}",
            f"- profit_factor: {metrics.profit_factor:.2f}",
            f"- win_rate: {metrics.win_rate:.2%}",
            f"- expectancy: {metrics.expectancy:.4f}",
            f"- recovery_factor: {metrics.recovery_factor:.2f}",
            f"- sharpe_ratio: {metrics.sharpe_ratio:.2f}",
            f"- sortino_ratio: {metrics.sortino_ratio:.2f}",
            f"- calmar_ratio: {metrics.calmar_ratio:.2f}",
            f"- avg_r: {metrics.avg_r:.2f}",
            f"- drawdown: {metrics.drawdown:.2f}",
            f"- risk_of_ruin: {metrics.risk_of_ruin:.4f}",
            f"- max_consecutive_losses: {metrics.max_consecutive_losses}",
            f"- max_consecutive_wins: {metrics.max_consecutive_wins}",
            f"- avg_holding_time_seconds: {metrics.avg_holding_time_seconds:.1f}",
            f"- capital_growth_rate: {metrics.capital_growth_rate:.2%}",
            f"- monte_carlo_confidence: {metrics.monte_carlo_confidence:.2%}",
            f"- parameter_sensitivity: {json.dumps(metrics.parameter_sensitivity or {}, ensure_ascii=False)}",
            f"- strategy_stability: {metrics.strategy_stability:.2%}",
            f"- out_of_sample_performance: {metrics.out_of_sample_performance:.2%}",
            f"- walk_forward_performance: {metrics.walk_forward_performance:.2%}",
            "",
            "## EXIT MODEL RANKINGS",
            json.dumps(exit_rankings, ensure_ascii=False, indent=2),
            "",
            "## PORTFOLIO STATE",
            json.dumps(portfolio_state, ensure_ascii=False, indent=2),
        ]
        report = "\n".join(lines)
        path = os.path.join("research", "latest_report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(report)
        return report

    def _to_dict(self, m: ScientificMetrics) -> dict[str, Any]:
        return {
            "profit_factor": m.profit_factor,
            "win_rate": m.win_rate,
            "expectancy": m.expectancy,
            "recovery_factor": m.recovery_factor,
            "sharpe_ratio": m.sharpe_ratio,
            "sortino_ratio": m.sortino_ratio,
            "calmar_ratio": m.calmar_ratio,
            "avg_r": m.avg_r,
            "drawdown": m.drawdown,
            "risk_of_ruin": m.risk_of_ruin,
            "max_consecutive_losses": m.max_consecutive_losses,
            "max_consecutive_wins": m.max_consecutive_wins,
            "avg_holding_time_seconds": m.avg_holding_time_seconds,
            "capital_growth_rate": m.capital_growth_rate,
            "monte_carlo_confidence": m.monte_carlo_confidence,
            "parameter_sensitivity": m.parameter_sensitivity,
            "strategy_stability": m.strategy_stability,
            "out_of_sample_performance": m.out_of_sample_performance,
            "walk_forward_performance": m.walk_forward_performance,
        }

    def _risk_of_ruin(self, win_rate: float, avg_win: float, avg_loss: float) -> float:
        if avg_loss <= 0 or avg_win <= 0 or not (0 < win_rate < 1):
            return 1.0
        r = (avg_win / avg_loss) * win_rate - (1 - win_rate)
        if r <= 0:
            return 1.0
        return min(1.0, ((1 - r) / (1 + r)) ** 100)

    def _growth_rate(self, equity: list[float]) -> float:
        if len(equity) < 2 or equity[0] == 0:
            return 0.0
        return (equity[-1] - equity[0]) / abs(equity[0])

    def _monte_carlo_confidence(self, profits: list[float], simulations: int = 1000) -> float:
        if len(profits) < 10:
            return 0.0
        base_mean = mean(profits)
        base_std = stdev(profits) if len(profits) > 1 else 0.0
        if base_std <= 0:
            return 1.0 if base_mean > 0 else 0.0
        positive = 0
        for _ in range(simulations):
            run = sum(random.gauss(base_mean, base_std) for _ in range(len(profits)))
            if run > 0:
                positive += 1
        return positive / simulations

    def _parameter_sensitivity(self, trades: list[dict[str, Any]]) -> dict[str, float]:
        by_param: dict[str, list[float]] = {}
        for t in trades:
            ps = t.get("parameter_set") or {}
            for k, v in ps.items():
                try:
                    fv = float(v)
                except Exception:
                    continue
                by_param.setdefault(k, []).append(float(t.get("profit", 0.0) or 0.0))
        sensitivity: dict[str, float] = {}
        for k, profits in by_param.items():
            if len(profits) > 1:
                sensitivity[k] = stdev(profits)
        return sensitivity

    def _strategy_stability(self, trades: list[dict[str, Any]]) -> float:
        by_strategy: dict[str, list[float]] = {}
        for t in trades:
            by_strategy.setdefault(t.get("strategy", "unknown"), []).append(float(t.get("profit", 0.0) or 0.0))
        if not by_strategy:
            return 0.0
        stabilities = []
        for profits in by_strategy.values():
            if len(profits) > 1:
                m = mean(profits)
                s = stdev(profits)
                stabilities.append(1.0 / (1.0 + abs(s)) if math.isfinite(s) else 0.0)
        return mean(stabilities) if stabilities else 0.0

    def _out_of_sample(self, trades: list[dict[str, Any]]) -> float:
        if len(trades) < 20:
            return 0.0
        split = int(len(trades) * 0.7)
        train = trades[:split]
        test = trades[split:]
        train_pf = self._profit_factor_for_trades(train)
        test_pf = self._profit_factor_for_trades(test)
        if train_pf <= 0:
            return 0.0
        return max(0.0, min(1.0, test_pf / train_pf))

    def _walk_forward(self, trades: list[dict[str, Any]]) -> float:
        if len(trades) < 40:
            return 0.0
        window = 20
        scores = []
        for start in range(0, len(trades) - window + 1, window):
            segment = trades[start:start + window]
            scores.append(self._profit_factor_for_trades(segment))
        if not scores:
            return 0.0
        consistency = 1.0 - (stdev(scores) / (mean(scores) if mean(scores) != 0 else 1.0))
        return max(0.0, min(1.0, consistency))

    def _profit_factor_for_trades(self, trades: list[dict[str, Any]]) -> float:
        wins = [float(t.get("profit", 0.0) or 0.0) for t in trades if float(t.get("profit", 0.0) or 0.0) > 0]
        losses = [abs(float(t.get("profit", 0.0) or 0.0)) for t in trades if float(t.get("profit", 0.0) or 0.0) <= 0]
        gp = sum(wins)
        gl = sum(losses)
        return gp / gl if gl > 0 else (999.0 if gp > 0 else 0.0)
