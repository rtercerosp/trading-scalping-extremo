# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from utils.utils import Utils
from utils.symbol_utils import normalize_symbol
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from logging import getLogger
import json
import os
import config

logger = getLogger(__name__)
METHOD_VERSION = config.STRATEGY_VERSION

class MethodVersion:
    def __init__(self, version_id: str, name: str, config: dict, description: str = ""):
        self.version_id = version_id
        self.name = name
        self.config = config
        self.description = description
        self.created_at = Utils.dateprint()
        self.active = False


class TradeMetrics:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.max_drawdown = 0.0
        self.max_consecutive_wins = 0
        self.max_consecutive_losses = 0
        self.avg_profit_per_win = 0.0
        self.avg_loss_per_loss = 0.0
        self.profit_factor = 0.0
        self.win_rate = 0.0
        self.expectancy = 0.0
        self.sharpe_ratio = 0.0
        self.avg_trade_duration_seconds = 0.0
        self.tp1_hits = 0
        self.tp2_hits = 0
        self.sl_hits = 0
        self.tp1_hit_rate = 0.0
        self.tp2_hit_rate = 0.0
        self.sl_hit_rate = 0.0
        self.breakeven_moves = 0
        self.breakeven_success_rate = 0.0
        self.total_volume = 0.0
        self.avg_volume = 0.0
        self.risk_reward_ratio = 0.0

    def update_from_trades(self, trades: List[dict]) -> None:
        if not trades:
            return

        self.total_trades = len(trades)
        self.winning_trades = sum(1 for t in trades if t.get("profit", 0) > 0)
        self.losing_trades = sum(1 for t in trades if t.get("profit", 0) < 0)
        self.total_profit = sum(t.get("profit", 0) for t in trades if t.get("profit", 0) > 0)
        self.total_loss = abs(sum(t.get("profit", 0) for t in trades if t.get("profit", 0) < 0))
        self.total_volume = sum(t.get("volume", 0) for t in trades)
        self.avg_volume = self.total_volume / self.total_trades if self.total_trades > 0 else 0.0

        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades

        if self.winning_trades > 0:
            self.avg_profit_per_win = self.total_profit / self.winning_trades

        if self.losing_trades > 0:
            self.avg_loss_per_loss = self.total_loss / self.losing_trades

        if self.total_loss > 0:
            self.profit_factor = self.total_profit / self.total_loss
        else:
            self.profit_factor = float('inf') if self.total_profit > 0 else 0.0

        if self.avg_loss_per_loss > 0:
            self.risk_reward_ratio = self.avg_profit_per_win / self.avg_loss_per_loss

        self.expectancy = (self.win_rate * self.avg_profit_per_win) - ((1 - self.win_rate) * self.avg_loss_per_loss)

        balance = 0.0
        peak = 0.0
        current_dd = 0.0
        for trade in trades:
            balance += trade.get("profit", 0)
            if balance > peak:
                peak = balance
            dd = peak - balance
            if dd > current_dd:
                current_dd = dd
        self.max_drawdown = current_dd

        consecutive = 0
        max_win_streak = 0
        max_loss_streak = 0
        for trade in trades:
            if trade.get("profit", 0) > 0:
                consecutive += 1
                max_win_streak = max(max_win_streak, consecutive)
            else:
                consecutive = -1
                max_loss_streak = max(max_loss_streak, abs(consecutive))
        self.max_consecutive_wins = max_win_streak
        self.max_consecutive_losses = max_loss_streak

        profits = [t.get("profit", 0) for t in trades]
        if len(profits) > 1:
            avg_profit = sum(profits) / len(profits)
            variance = sum((p - avg_profit) ** 2 for p in profits) / (len(profits) - 1)
            std_dev = variance ** 0.5
            if std_dev > 0:
                self.sharpe_ratio = (avg_profit / std_dev) * (len(profits) ** 0.5)

        durations = []
        for trade in trades:
            entry_time = trade.get("entry_time")
            exit_time = trade.get("exit_time")
            if entry_time and exit_time:
                try:
                    entry = datetime.fromisoformat(entry_time)
                    exit_ = datetime.fromisoformat(exit_time)
                    durations.append((exit_ - entry).total_seconds())
                except (ValueError, TypeError):
                    logger.debug("EVALUATOR: No se pudo parsear fecha para duración de trade: %s, %s", entry_time, exit_time)
        if durations:
            self.avg_trade_duration_seconds = sum(durations) / len(durations)

        self.tp1_hits = sum(1 for t in trades if t.get("exit_reason") == "TP1")
        self.tp2_hits = sum(1 for t in trades if t.get("exit_reason") == "TP2")
        self.sl_hits = sum(1 for t in trades if t.get("exit_reason") == "SL")
        self.breakeven_moves = sum(1 for t in trades if t.get("exit_reason") == "BREAKEVEN")
        closed_count = self.total_trades if self.total_trades > 0 else 1
        self.tp1_hit_rate = self.tp1_hits / closed_count
        self.tp2_hit_rate = self.tp2_hits / closed_count
        self.sl_hit_rate = self.sl_hits / closed_count
        self.breakeven_success_rate = self.breakeven_moves / closed_count


class InstitutionalEvaluator:
    def __init__(self, trade_history: List[dict], method_version: str = METHOD_VERSION):
        self.trade_history = [t.to_dict() if hasattr(t, "to_dict") else t for t in trade_history]
        self.method_version = method_version
        self.metrics_by_symbol: Dict[str, TradeMetrics] = {}
        self.global_metrics = TradeMetrics("GLOBAL")
        self.versions_file = "trading_method_versions.json"
        self.measurements_file = "trading_method_measurements.json"
        self._load_versions()
        self._load_measurements()

    def _load_versions(self) -> None:
        if os.path.exists(self.versions_file):
            try:
                with open(self.versions_file, 'r') as f:
                    self.versions = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error("EVALUATOR: Error cargando versiones desde %s: %s", self.versions_file, e)
                self.versions = {}
        else:
            self.versions = {}

    def _save_versions(self) -> None:
        try:
            with open(self.versions_file, 'w') as f:
                json.dump(self.versions, f, indent=2)
        except Exception as e:
            logger.error("EVALUATOR: Error guardando versiones: %s", e, exc_info=True)

    def _load_measurements(self) -> None:
        if os.path.exists(self.measurements_file):
            try:
                with open(self.measurements_file, 'r') as f:
                    self.measurements = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error("EVALUATOR: Error cargando mediciones desde %s: %s", self.measurements_file, e)
                self.measurements = {}
        else:
            self.measurements = {}

    def _save_measurements(self) -> None:
        try:
            with open(self.measurements_file, 'w') as f:
                json.dump(self.measurements, f, indent=2)
        except Exception as e:
            logger.error("EVALUATOR: Error guardando mediciones: %s", e, exc_info=True)

    def register_version(self, version_id: str, name: str, config: dict, description: str = "", set_active: bool = False) -> None:
        version = MethodVersion(version_id, name, config, description)
        self.versions[version_id] = {
            "version_id": version.version_id,
            "name": version.name,
            "config": version.config,
            "description": version.description,
            "created_at": version.created_at,
            "active": set_active,
        }
        if set_active:
            for vid in self.versions:
                self.versions[vid]["active"] = (vid == version_id)
        self._save_versions()
        logger.info("EVALUATOR: Versión registrada: %s - %s", version_id, name)

    def set_active_version(self, version_id: str) -> None:
        if version_id not in self.versions:
            logger.warning("EVALUATOR: Versión %s no encontrada para activar", version_id)
            return
        for vid in self.versions:
            self.versions[vid]["active"] = (vid == version_id)
        self._save_versions()
        logger.info("EVALUATOR: Versión activa cambiada a %s", version_id)

    def get_active_version(self) -> Optional[dict]:
        for vid, vdata in self.versions.items():
            if vdata.get("active"):
                return vdata
        return None

    def _normalize_trade_history(self) -> None:
        self.trade_history = [t.to_dict() if hasattr(t, "to_dict") else t for t in self.trade_history]

    def compute_all_metrics(self, current_symbols: Optional[List[str]] = None) -> Dict[str, TradeMetrics]:
        self._normalize_trade_history()
        self.metrics_by_symbol.clear()
        normalized_current_symbols = {normalize_symbol(s) for s in current_symbols} if current_symbols else set()
        trades_by_symbol: Dict[str, List[dict]] = {}
        for trade in self.trade_history:
            if trade.get("exit_reason") == "OPEN":
                continue
            symbol = normalize_symbol(trade.get("symbol", "UNKNOWN"))
            if normalized_current_symbols and symbol not in normalized_current_symbols:
                continue
            trades_by_symbol.setdefault(symbol, []).append(trade)

        for symbol, trades in trades_by_symbol.items():
            metrics = TradeMetrics(symbol)
            metrics.update_from_trades(trades)
            self.metrics_by_symbol[symbol] = metrics

        all_closed = [t for t in self.trade_history if t.get("exit_reason") != "OPEN"]
        if normalized_current_symbols:
            all_closed = [t for t in all_closed if normalize_symbol(t.get("symbol", "")) in normalized_current_symbols]
        self.global_metrics = TradeMetrics("GLOBAL")
        self.global_metrics.update_from_trades(all_closed)

        return self.metrics_by_symbol

    def score_method(self) -> dict:
        self._normalize_trade_history()
        if not self.trade_history:
            return {"score": 0.0, "grade": "N/A", "reason": "Sin trades"}

        closed = [t for t in self.trade_history if t.get("exit_reason") != "OPEN"]
        if not closed:
            return {"score": 0.0, "grade": "N/A", "reason": "Sin trades cerrados"}

        self.compute_all_metrics()
        m = self.global_metrics

        score = 0.0
        score += m.win_rate * 40
        score += max(0.0, min(1.0, m.profit_factor / 3.0)) * 25
        score += max(0.0, min(1.0, m.expectancy / 0.5)) * 20
        score += max(0.0, min(1.0, m.sharpe_ratio / 2.0)) * 15

        if m.max_consecutive_losses >= 10:
            score -= 10
        elif m.max_consecutive_losses >= 7:
            score -= 5

        if m.max_drawdown > 0.2 * abs(sum(t.get("profit", 0) for t in closed)):
            score -= 10

        score = max(0.0, min(100.0, score))

        if score >= 85:
            grade = "A - Excelente"
        elif score >= 70:
            grade = "B - Bueno"
        elif score >= 55:
            grade = "C - Regular"
        elif score >= 40:
            grade = "D - Deficiente"
        else:
            grade = "F - Crítico"

        return {
            "score": round(score, 2),
            "grade": grade,
            "win_rate": round(m.win_rate, 4),
            "profit_factor": round(m.profit_factor, 4),
            "expectancy": round(m.expectancy, 4),
            "sharpe_ratio": round(m.sharpe_ratio, 4),
            "max_drawdown": round(m.max_drawdown, 4),
            "max_consecutive_losses": m.max_consecutive_losses,
            "total_trades": m.total_trades,
            "reason": f"Win rate {m.win_rate:.1%}, PF {m.profit_factor:.2f}, Exp {m.expectancy:.4f}",
        }

    def save_measurement(self, label: str, extra: dict = None) -> None:
        self._normalize_trade_history()
        score_data = self.score_method()
        measurement = {
            "timestamp": datetime.utcnow().isoformat(),
            "method_version": self.method_version,
            "active_version": self.get_active_version().get("version_id") if self.get_active_version() else None,
            "label": label,
            "score": score_data.get("score"),
            "grade": score_data.get("grade"),
            "win_rate": score_data.get("win_rate"),
            "profit_factor": score_data.get("profit_factor"),
            "expectancy": score_data.get("expectancy"),
            "sharpe_ratio": score_data.get("sharpe_ratio"),
            "max_drawdown": score_data.get("max_drawdown"),
            "max_consecutive_losses": score_data.get("max_consecutive_losses"),
            "total_trades": score_data.get("total_trades"),
            "reason": score_data.get("reason"),
        }
        if extra:
            measurement.update(extra)
        self.measurements.setdefault(self.method_version, []).append(measurement)
        self._save_measurements()
        print(f"{Utils.dateprint()} - EVALUATOR: Medición guardada [{label}] Score={score_data.get('score')} Grade={score_data.get('grade')}")

    def get_institutional_report(self, current_symbols: Optional[List[str]] = None) -> str:
        self._normalize_trade_history()
        normalized_current_symbols = {normalize_symbol(s) for s in current_symbols} if current_symbols else set()
        if not self.trade_history:
            return "Sin datos para evaluación institucional."

        score_data = self.score_method()
        closed = [t for t in self.trade_history if t.get("exit_reason") != "OPEN"]
        open_trades = [t for t in self.trade_history if t.get("exit_reason") == "OPEN"]

        report = f"\n{'='*60}\n"
        report += f"EVALUACIÓN INSTITUCIONAL - {self.method_version}\n"
        report += f"{'='*60}\n\n"

        report += f"PUNTAJE GENERAL: {score_data.get('score')}/100 - {score_data.get('grade')}\n"
        report += f"Justificación: {score_data.get('reason')}\n\n"

        report += f"--- Métricas Globales ---\n"
        report += f"Trades cerrados: {score_data.get('total_trades')}\n"
        report += f"Win Rate: {score_data.get('win_rate', 0):.2%}\n"
        report += f"Profit Factor: {score_data.get('profit_factor', 0):.2f}\n"
        report += f"Expectancy: {score_data.get('expectancy', 0):.4f}\n"
        report += f"Sharpe Ratio: {score_data.get('sharpe_ratio', 0):.2f}\n"
        report += f"Max Drawdown: {score_data.get('max_drawdown', 0):.2f}\n"
        report += f"Max Consecutive Losses: {score_data.get('max_consecutive_losses')}\n\n"

        if open_trades:
            report += f"Trades abiertos: {len(open_trades)}\n\n"

        if self.metrics_by_symbol:
            report += f"--- Rendimiento por Activo ---\n"
            for symbol, metrics in sorted(self.metrics_by_symbol.items()):
                if normalized_current_symbols and symbol not in normalized_current_symbols:
                    continue
                report += (
                    f"{symbol}: trades={metrics.total_trades}, "
                    f"win_rate={metrics.win_rate:.1%}, "
                    f"PF={metrics.profit_factor:.2f}, "
                    f"TP1_hit={metrics.tp1_hit_rate:.1%}, "
                    f"TP2_hit={metrics.tp2_hit_rate:.1%}, "
                    f"SL_hit={metrics.sl_hit_rate:.1%}, "
                    f"BE_moves={metrics.breakeven_moves}\n"
                )
            report += "\n"

        active_version = self.get_active_version()
        if active_version:
            report += f"--- Versión Activa ---\n"
            report += f"ID: {active_version.get('version_id')}\n"
            report += f"Nombre: {active_version.get('name')}\n"
            report += f"Descripción: {active_version.get('description', '')}\n"
            report += f"Creada: {active_version.get('created_at')}\n\n"

        if self.measurements.get(self.method_version):
            report += f"--- Historial de Mediciones ---\n"
            measurements = self.measurements[self.method_version][-10:]
            for m in measurements:
                score = m.get("score")
                grade = m.get("grade")
                win_rate = m.get("win_rate") or 0
                report += (
                    f"[{m.get('timestamp')}] {m.get('label')}: "
                    f"Score={score}, Grade={grade}, "
                    f"WR={win_rate:.1%}\n"
                )
            report += "\n"

        report += f"{'='*60}\n"
        return report

    def get_best_version(self) -> Optional[dict]:
        best_score = -1
        best_version = None
        for vid, vdata in self.versions.items():
            if vdata.get("active"):
                continue
            measurements = self.measurements.get(vid, [])
            if measurements:
                avg_score = sum(m.get("score", 0) for m in measurements) / len(measurements)
                if avg_score > best_score:
                    best_score = avg_score
                    best_version = vdata
        return best_version

    def recommend_version_switch(self) -> Optional[str]:
        best = self.get_best_version()
        active = self.get_active_version()
        if not best or not active:
            return None
        if best.get("version_id") == active.get("version_id"):
            return None
        best_avg = sum(m.get("score", 0) for m in self.measurements.get(best.get("version_id", ""), [])) / max(1, len(self.measurements.get(best.get("version_id", ""), [])))
        active_avg = sum(m.get("score", 0) for m in self.measurements.get(active.get("version_id", ""), [])) / max(1, len(self.measurements.get(active.get("version_id", ""), [])))
        if active_avg >= best_avg:
            return None
        if best_avg > active_avg + 8:
            return best.get("version_id")
        return None
