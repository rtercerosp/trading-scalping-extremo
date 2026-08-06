# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import logging
from queue import Queue
from brain.performance_tracker import PerformanceTracker
from brain.trade_history_manager import TradeHistoryManager
from data_provider.data_provider import DataProvider
from platform_connector.platform_connector import PlatformConnector
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor
from events.events import ExecutionEvent, DataEvent
from utils.utils import Utils
from typing import Dict, List
import json
import os
import time
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from utils.symbol_utils import get_asset_category, normalize_symbol
import config


AI_RUNTIME_VERSION = "V9_SCALPING_MAX_QUALITY"


from brain.models import TradeRecord


class TradingBrain:
    def __init__(self, events_queue: Queue, data_provider: DataProvider, portfolio: Portfolio,
                 order_executor: OrderExecutor, connector: PlatformConnector, news_protection=None):
        self.events_queue = events_queue
        self.data_provider = data_provider
        self.portfolio = portfolio
        self.order_executor = order_executor
        self.connector = connector
        self.news_protection = news_protection

        self.break_even_manager = None

        self.trade_history_manager = TradeHistoryManager()
        self.performance_tracker = PerformanceTracker()
        self.news_decisions: Dict[str, Dict] = {}

        self.trade_history = self.trade_history_manager.trade_history
        self.successful_trades = self.trade_history_manager.successful_trades
        self.failed_trades = self.trade_history_manager.failed_trades
        self.asset_performance = self.performance_tracker.asset_performance
        self.strategy_performance = self.performance_tracker.strategy_performance

        self.brain_enabled = True
        self.learning_rate = 0.1
        self.min_trades_for_learning = 5
        self._last_scan_ts: float = 0.0
        self._scan_interval_seconds = 30
        self._last_eval_ts: float = 0.0
        self._eval_interval_seconds = 300

        self._consecutive_losses = 0
        self._max_consecutive_losses = 3
        self._daily_loss_pct_limit = 0.02
        self._daily_start_balance = 0.0
        self._circuit_breaker_active = False
        self._circuit_breaker_reason = None

        try:
            from ai.trading_ai import TradingAI
            self.ai = TradingAI(storage_path=os.path.join("ai", AI_RUNTIME_VERSION.lower()))
            self.ai_enabled = True
        except Exception as e:
            logging.error("BRAIN: No se pudo inicializar TradingAI: %s", e, exc_info=True)
            self.ai_enabled = False

        from brain.trading_method_evaluator import InstitutionalEvaluator, METHOD_VERSION
        self.evaluator = InstitutionalEvaluator(
            trade_history=self.trade_history,
            method_version=METHOD_VERSION,
        )
        if METHOD_VERSION not in self.evaluator.versions:
            self.evaluator.register_version(
                METHOD_VERSION,
                "Scalping Extremo V5 Asset Isolated Guarded",
                {
                    "timeframe": "5min",
                    "trend_timeframe": "15min",
                    "risk_pct": 0.01,
                    "max_leverage_factor": 3,
                    "sl_atr_mult": 1.2,
                    "tp_atr_mult": 2.0,
                    "max_total_positions": 8,
                    "max_positions_per_symbol": 2,
                    "max_positions_by_category": {"crypto": 4, "forex": 6},
                    "max_volume_btc": 0.02,
                    "max_volume_eth": 0.02,
                    "max_volume_sol": 0.02,
                    "strategy": "Asset_Isolated_Guarded_Category_Based",
                    "spread_buffer": "1.5x spread + 20 pts",
                    "atr_min_btc": 200,
                    "atr_min_eth": 100,
                    "ai_enabled": True,
                    "ai_features": ["market_regime_detection", "strategy_selection", "per_asset_learning", "gold_guard_mode", "full_toolset_loading", "expert_rules_loading", "backtest_preloaded_scores", "news_aware_trading"],
                },
                "Version V7 con pre-carga de conocimiento via backtesting historico y reglas expertas. Motor de backtesting ejecuta las 10 estrategias sobre datos reales de MT5 para generar scores iniciales por estrategia/activo. Reglas expertas de correlacion inter-mercado (DXY, VIX, BTC.D, US10Y) y eventos macro (NFP, CPI, Fed, ECB) cargadas en TradingBrain. Acceso a ai/expert_rules.json y ai/backtest_results.json. IA inicia con conocimiento previo instead de cero, reduciendo trades ciegos y acelerando convergencia. Filtro de noticias activo para todos los activos; la IA decide si opera o no segun impacto y rendimiento historico. Compatible con V6; si no existe pre-carga, fallback a V6 puro.",
                set_active=True,
            )

        self.expert_rules = {}
        self._load_expert_rules()

        self.trade_history_manager.load()

    def _load_expert_rules(self) -> None:
        rules_path = os.path.join("ai", "expert_rules.json")
        if os.path.exists(rules_path):
            try:
                with open(rules_path, 'r', encoding="utf-8") as f:
                    self.expert_rules = json.load(f)
                print(f"{Utils.dateprint()} - BRAIN: Reglas expertas cargadas desde {rules_path}")
            except Exception as e:
                print(f"{Utils.dateprint()} - BRAIN: Error cargando reglas expertas: {e}")
                self.expert_rules = {}
        else:
            print(f"{Utils.dateprint()} - BRAIN: No se encontro {rules_path}, continuando sin reglas expertas")
            self.expert_rules = {}

    def resume_open_positions(self, magic_number: int) -> None:
        if self.break_even_manager is None:
            print(f"{Utils.dateprint()} - BRAIN: BreakEvenManager no disponible, no se pueden reanudar posiciones.")
            return
        try:
            self.break_even_manager.resume_open_positions(magic_number)
        except Exception as e:
            print(f"{Utils.dateprint()} - BRAIN: Error al reanudar posiciones abiertas: {e}")

    @staticmethod
    def _symbol_key(symbol: str) -> str:
        return normalize_symbol(symbol)

    def _update_asset_performance(self, symbol: str, profit: float) -> None:
        self.performance_tracker.update_asset_performance(symbol, profit)

    def _update_strategy_performance(self, symbol: str, strategy: str, profit: float) -> None:
        self.performance_tracker.update_strategy_performance(symbol, strategy, profit)

    def _compute_adaptive_params(self, symbol: str) -> dict:
        """
        Computes adaptive parameters by delegating to the AI LearningEngine.
        This method acts as a single point of access for adaptive parameters,
        ensuring the LearningEngine is the single source of truth.
        """
        symbol_key = self._symbol_key(symbol)
        if self.ai_enabled and hasattr(self, "ai") and self.ai is not None:
            return self.ai.get_adaptive_params(symbol_key)
        return {}

    def get_symbol_trade_state(self, symbol: str) -> dict:
        symbol_key = self._symbol_key(symbol)
        asset_category = get_asset_category(symbol_key)

        state = {
            "tradeable": True,
            "risk_override": None,
            "reason": None,
            "excluded": False,
        }

        if asset_category == "gold":
            return state

        perf = self.asset_performance.get(symbol_key)
        if not perf or perf.get("total_trades", 0) < 30:
            return state

        win_rate = perf.get("win_rate", 0.0)
        extreme_params = config.EXTREME_SCALPING_PARAMS.get(symbol_key, {})
        min_wr = extreme_params.get("min_win_rate_for_trading", 0.25)
        exclude_wr = extreme_params.get("exclude_if_win_rate_below", 0.20)

        if win_rate < exclude_wr:
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"win_rate {win_rate:.2f} por debajo del umbral mínimo {exclude_wr:.2f}",
            })
            return state

        if win_rate < min_wr:
            state.update({
                "tradeable": True,
                "risk_override": max(0.002, config.LEARNING_ASSET_SPECIFIC_PARAMS.get(symbol_key, {}).get("risk_pct", 0.005) * 0.5),
                "reason": f"win_rate {win_rate:.2f} por debajo de {min_wr:.2f}, riesgo reducido al 50%",
            })
            return state

        if win_rate >= 0.60:
            state.update({
                "tradeable": True,
                "risk_override": min(0.015, config.LEARNING_ASSET_SPECIFIC_PARAMS.get(symbol_key, {}).get("risk_pct", 0.008) * 1.3),
                "reason": f"win_rate {win_rate:.2f} excelente, riesgo aumentado un 30%",
            })

        return state

    def is_symbol_tradeable(self, symbol: str) -> bool:
        return self.get_symbol_trade_state(symbol).get("tradeable", False)

    def get_extreme_scalping_params(self, symbol: str) -> dict:
        symbol_key = self._symbol_key(symbol)
        params = config.EXTREME_SCALPING_PARAMS.get(symbol_key, {})
        if not params:
            return {"enabled": True, "sl_atr_mult": 1.0, "tp_atr_mult": 2.5, "risk_pct": 0.008, "trailing_activation_pct": 0.003, "trailing_offset_pct": 0.0015}
        
        perf = self.asset_performance.get(symbol_key, {})
        win_rate = perf.get("win_rate", 0.5)
        total_trades = perf.get("total_trades", 0)
        
        result = dict(params)
        if total_trades >= 30 and win_rate < params.get("exclude_if_win_rate_below", 0.3):
            result["enabled"] = False
            result["reason"] = "low_win_rate"
        
        return result

    def get_zero_loss_params(self, symbol: str) -> dict:
        defaults = {
            "break_even_trigger_pct": getattr(config, "V10_BREAK_EVEN_TRIGGER_PCT", 0.30),
            "break_even_min_trigger_points": getattr(config, "V10_BREAK_EVEN_MIN_TRIGGER_POINTS", {}).get(symbol, 0),
            "break_even_max_trigger_points": getattr(config, "V10_BREAK_EVEN_MAX_TRIGGER_POINTS", {}).get(symbol, 0),
            "break_even_buffer_points": 2,
            "broker_cost_coverage": getattr(config, "V10_BROKER_COST_COVERAGE", {}).get(symbol, {"spread_points": 0, "commission_per_lot": 0.0, "min_profit_points": 0}),
            "reverse_protection_pct": getattr(config, "V10_REVERSE_PROTECTION_PCT", 0.25),
            "gap_protection_pct": getattr(config, "V10_GAP_PROTECTION_PCT", 0.003),
            "pre_breakeven_max_sl_improvement_pct": getattr(config, "V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT", 0.15),
            "trailing_aggressive_activation_pct": getattr(config, "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT", 0.003),
            "trailing_aggressive_offset_points": getattr(config, "V10_TRAILING_AGGRESSIVE_OFFSET_POINTS", {}).get(symbol, 20),
            "compounding_volume_multiplier": getattr(config, "V10_COMPOUNDING_VOLUME_MULTIPLIER", 2.0),
            "compounding_min_equity": getattr(config, "V10_COMPOUNDING_MIN_EQUITY", 5000.0),
            "spread_max_points_multiplier": getattr(config, "V10_SPREAD_MAX_POINTS_MULTIPLIER", 1.5),
            "min_broker_coverage_points": getattr(config, "V10_MIN_BROKER_COVERAGE_POINTS", 2),
            "max_volume_per_candle_ratio": getattr(config, "V10_MAX_VOLUME_PER_CANDLE_RATIO", 0.05),
        }
        return defaults

    def record_execution(self, execution_event: ExecutionEvent) -> None:
        if not self.brain_enabled:
            return

        exit_reason = getattr(execution_event, 'exit_reason', 'OPEN') or 'OPEN'

        if exit_reason != "OPEN":
            record = self.trade_history_manager.get_open_trade(execution_event.symbol)
            if record:
                record.exit_price = execution_event.fill_price
                record.exit_reason = exit_reason
                record.profit = 0.0
                record.closed_deal_ticket = getattr(execution_event, 'deal_ticket', 0)
                record.position_ticket = getattr(execution_event, 'position_ticket', 0)
                self.trade_history_manager.save()
            return

        record = TradeRecord(
            symbol=execution_event.symbol,
            signal=execution_event.signal.value if hasattr(execution_event.signal, 'value') else str(execution_event.signal),
            entry_price=execution_event.entry_price,
            sl=execution_event.initial_sl,
            tp1=execution_event.tp1,
            tp2=execution_event.tp2,
            volume=execution_event.volume,
            exit_price=execution_event.entry_price,
            exit_reason="OPEN",
            profit=0.0,
            strategy=execution_event.strategy_name or execution_event.strategy_type,
            deal_ticket=getattr(execution_event, 'deal_ticket', 0),
            position_ticket=getattr(execution_event, 'position_ticket', 0),
        )
        self.trade_history_manager.add_trade(record)

    def update_trade_result(self, symbol: str, exit_price: float, exit_reason: str, profit: float, closed_deal_ticket: int = 0) -> None:
        if not self.brain_enabled:
            return

        strategy = "UNKNOWN"
        record = self.trade_history_manager.get_open_trade(symbol)
        if record:
            strategy = record.strategy or "UNKNOWN"
            record.exit_price = exit_price
            record.exit_reason = exit_reason
            record.profit = profit
            record.closed_deal_ticket = closed_deal_ticket
            self.trade_history_manager.save()

        self._update_asset_performance(symbol, profit)
        self._update_strategy_performance(symbol, strategy, profit)

        if profit < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        account_info = self.connector.get_account_info() if self.connector else None
        current_balance = account_info.balance if account_info else 0.0
        if self._daily_start_balance <= 0 and current_balance > 0:
            self._daily_start_balance = current_balance
        if self._daily_start_balance > 0 and current_balance > 0:
            daily_drawdown = (self._daily_start_balance - current_balance) / self._daily_start_balance
            if daily_drawdown >= self._daily_loss_pct_limit or self._consecutive_losses >= self._max_consecutive_losses:
                self._circuit_breaker_active = True
                self._circuit_breaker_reason = (
                    f"drawdown diario {daily_drawdown:.2%}" if daily_drawdown >= self._daily_loss_pct_limit
                    else f"{self._consecutive_losses} pérdidas consecutivas"
                )
                logging.critical("CIRCUIT BREAKER ACTIVADO: %s. Trading detenido por hoy.", self._circuit_breaker_reason)

        if self.ai_enabled and hasattr(self, 'ai') and self.ai is not None:
            try:
                sl_hit = exit_reason == "SL"
                tp_hit = exit_reason in ("TP", "TP1", "TP2")
                if getattr(config, "STRATEGY_VERSION", "") == "V10_ZERO_LOSS_SCALPING":
                    if profit < 0:
                        sl_hit = True
                        tp_hit = False
                    elif profit > 0 and exit_reason in ("BREAK_EVEN", "REVERSE_PROTECTION"):
                        tp_hit = True
                        sl_hit = False
                self.ai.learn_from_trade(symbol, strategy, profit, sl_hit, tp_hit)
            except Exception as e:
                logging.error("BRAIN: Error en aprendizaje AI para %s: %s", symbol, e, exc_info=True)

    def is_circuit_breaker_active(self) -> tuple[bool, str | None]:
        return self._circuit_breaker_active, self._circuit_breaker_reason

    def reset_daily_circuit_breaker(self) -> None:
        self._circuit_breaker_active = False
        self._circuit_breaker_reason = None
        self._consecutive_losses = 0
        account_info = self.connector.get_account_info() if self.connector else None
        self._daily_start_balance = account_info.balance if account_info else 0.0

    def scan_closed_positions(self, connector: PlatformConnector) -> None:
        if not self.brain_enabled:
            return

        now_ts = time.time()
        if now_ts - self._last_scan_ts < self._scan_interval_seconds:
            return
        self._last_scan_ts = now_ts

        try:
            utc_now = datetime.utcnow()
            from_date = utc_now - timedelta(days=90)

            history_deals = connector.get_history_deals(from_date=from_date, to_date=utc_now)
            if not history_deals:
                return

            processed_deals = set()
            for record in self.trade_history_manager.trade_history:
                if record.closed_deal_ticket:
                    processed_deals.add(record.closed_deal_ticket)

            for deal in history_deals:
                if deal.ticket in processed_deals:
                    continue

                if deal.entry != mt5.DEAL_ENTRY_OUT:
                    continue

                symbol = deal.symbol
                profit = deal.profit
                exit_price = deal.price
                position_id = getattr(deal, 'position_id', 0)

                exit_reason = "TP" if deal.reason == mt5.DEAL_REASON_TP else "SL" if deal.reason == mt5.DEAL_REASON_SL else "CLOSED"

                symbol_key = self._symbol_key(symbol)
                matching_record = None
                if position_id > 0:
                    matching_record = next(
                        (record for record in reversed(self.trade_history_manager.trade_history)
                         if self._symbol_key(record.symbol) == symbol_key and record.exit_reason == "OPEN" and record.position_ticket == position_id),
                        None,
                    )

                if not matching_record:
                    matching_record = next(
                        (record for record in reversed(self.trade_history_manager.trade_history)
                         if self._symbol_key(record.symbol) == symbol_key and record.exit_reason == "OPEN"),
                        None,
                    )

                if matching_record:
                    if exit_reason == "TP" and matching_record.tp1 > 0 and matching_record.tp2 > 0 and matching_record.tp1 != matching_record.tp2:
                        if abs(exit_price - matching_record.tp1) <= abs(exit_price - matching_record.tp2):
                            exit_reason = "TP1"
                        else:
                            exit_reason = "TP2"

                    matching_record.exit_price = exit_price
                    matching_record.exit_reason = exit_reason
                    matching_record.profit = profit
                    matching_record.closed_deal_ticket = deal.ticket

                    self._update_asset_performance(symbol, profit)
                    self._update_strategy_performance(symbol, matching_record.strategy, profit)

                    if self.ai_enabled and hasattr(self, 'ai') and self.ai is not None:
                        try:
                            sl_hit = exit_reason == "SL"
                            tp_hit = exit_reason in ("TP", "TP1", "TP2")
                            self.ai.learn_from_trade(symbol, matching_record.strategy, profit, sl_hit, tp_hit)
                        except Exception as e:
                            logging.error("BRAIN: Error en aprendizaje AI para %s: %s", symbol, e, exc_info=True)

                processed_deals.add(deal.ticket)

        except Exception as e:
            print(f"{Utils.dateprint()} - BRAIN: Error al escanear posiciones cerradas: {e}")

        self.trade_history_manager.save()

    def maybe_run_evaluation(self, label: str = "periodic", extra: dict = None) -> None:
        if not self.brain_enabled:
            return
        now_ts = time.time()
        if now_ts - self._last_eval_ts < self._eval_interval_seconds:
            return
        self._last_eval_ts = now_ts
        self.evaluator.trade_history = self.trade_history
        self.evaluator.compute_all_metrics()
        self.evaluator.save_measurement(label=label, extra=extra)
        recommendation = self.evaluator.recommend_version_switch()
        if recommendation:
            print(f"{Utils.dateprint()} - EVALUATOR: Se recomienda cambiar a la versión {recommendation}")
            print(f"{Utils.dateprint()} - EVALUATOR: Cambio de versión desactivado temporalmente. Versión activa: {self.evaluator.get_active_version().get('version_id') if self.evaluator.get_active_version() else 'N/A'}")

    def get_institutional_report(self, current_symbols: list | None = None) -> str:
        self.evaluator.trade_history = self.trade_history
        return self.evaluator.get_institutional_report(current_symbols=current_symbols)

    def get_adaptive_params(self, symbol: str) -> dict:
        return self._compute_adaptive_params(symbol)

    def get_asset_timeframes(self, symbol: str) -> dict:
        symbol_key = self._symbol_key(symbol)
        asset_category = get_asset_category(symbol_key)
        config = {
            "crypto": {"entry": "15min", "trend": "30min", "rsi": "15min"},
            "gold": {"entry": "15min", "trend": "30min", "rsi": "15min"},
            "forex": {"entry": "5min", "trend": "15min", "rsi": "5min"},
        }
        return config.get(asset_category, config["forex"])

    def get_asset_risk_overrides(self, symbol: str) -> dict:
        symbol_key = self._symbol_key(symbol)
        asset_category = get_asset_category(symbol_key)
        config = {
            "crypto": {"sl_atr_mult": 1.4, "tp_atr_mult": 2.2, "rsi_upper": 72.0, "rsi_lower": 28.0},
            "gold": {"sl_atr_mult": 1.3, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0},
            "forex": {"sl_atr_mult": 1.2, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0},
        }
        return config.get(asset_category, config["forex"])

    def should_block_for_news(self, symbol: str) -> tuple:
        symbol_key = self._symbol_key(symbol)
        if not self.news_protection or not self.news_protection.enabled:
            return False, {}

        news_info = self.news_protection.get_news_info_for_symbol(symbol)
        if not news_info.get("in_window"):
            return False, {}

        perf = self.asset_performance.get(symbol_key, {})
        active_events = news_info.get("active", [])

        decision_info = {
            "news": active_events,
            "win_rate": perf.get("win_rate", 0.0),
            "total_trades": perf.get("total_trades", 0),
        }

        max_impact = "LOW"
        for event in active_events:
            if event.get("impact") == "HIGH":
                max_impact = "HIGH"
                break
            if event.get("impact") == "MEDIUM":
                max_impact = "MEDIUM"

        if max_impact == "HIGH":
            decision_info["risk_pct_override"] = 0.005
            decision_info["reason"] = ("high_impact_news_reduced_risk"
                                     if decision_info["total_trades"] < 20 or decision_info["win_rate"] < 0.45
                                     else "high_impact_news_acceptable_performance")
            return False, decision_info

        elif max_impact == "MEDIUM":
            decision_info["risk_pct_override"] = 0.005
            decision_info["reason"] = ("medium_impact_news_reduced_risk"
                                     if decision_info["total_trades"] < 10 or decision_info["win_rate"] < 0.35
                                     else "medium_impact_news_acceptable_performance")
            return False, decision_info

        decision_info["reason"] = "low_impact_news"
        return False, decision_info

    def record_news_decision(self, symbol: str, decision: str, news_info: dict) -> None:
        symbol_key = self._symbol_key(symbol)
        self.news_decisions[symbol_key] = {
            "decision": decision,
            "timestamp": datetime.now().isoformat(),
            "news_info": news_info,
        }

    def get_strategy_recommendation(self, symbol: str, asset_category: str) -> list[str]:
        symbol_key = self._symbol_key(symbol)
        available = [s.__class__.__name__ for s in getattr(self, '_current_strategies', [])]
        available = [name for name in available if not self._is_strategy_in_probation(symbol_key, name)]

        if not available:
            return []

        if self.ai_enabled and hasattr(self, 'ai') and self.ai is not None:
            try:
                primary = self.ai.select_strategy(symbol_key, available)
                if primary in available:
                    remaining = [name for name in available if name != primary]
                    order = [primary]
                    if asset_category == "gold":
                        order.extend([name for name in remaining if name in ("SignalTrendPullback", "SignalBreakout", "SignalFibScalp", "SignalRSI", "SignalMACrossover")])
                    elif asset_category == "crypto":
                        order.extend([name for name in remaining if name in ("SignalMomentum", "SignalBreakout", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalBTCStructureBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover")])
                    else:
                        order.extend([name for name in remaining if name in ("SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover", "SignalEURUSDExtreme", "SignalGBPExtreme", "SignalUSDJPExtreme")])
                    order.extend([name for name in remaining if name not in order])
                    return order
            except Exception as e:
                logging.error("BRAIN: Error seleccionando estrategia para %s: %s", symbol_key, e, exc_info=True)

        strat_perf = self.strategy_performance.get(symbol_key, {})
        if strat_perf:
            def strategy_score(item):
                stats = item[1]
                trades = stats.get("trades", 0)
                if trades < 5:
                    return 0.0
                win_rate = stats.get("win_rate", 0.0)
                profit_factor = stats.get("gross_profit", 0.0) / stats.get("gross_loss", 0.0) if stats.get("gross_loss", 0.0) > 0 else (float('inf') if stats.get("gross_profit", 0.0) > 0 else 0.0)
                profit = stats.get("profit", 0.0)
                if getattr(config, "STRATEGY_VERSION", "") == "V10_ZERO_LOSS_SCALPING":
                    return win_rate * 0.6 + min(profit_factor, 4.0) * 0.3 + min(trades / 50.0, 1.0) * 0.1
                return win_rate * 0.4 + min(profit_factor, 3.0) * 0.3 + min(trades / 50.0, 1.0) * 0.3

            ranked = sorted(strat_perf.items(), key=strategy_score, reverse=True)
            best_strategy = ranked[0][0] if ranked else None
            if best_strategy and best_strategy in available:
                order = [best_strategy]
                order.extend([name for name in available if name != best_strategy])
                return order

        perf = self.asset_performance.get(symbol_key, {})
        win_rate = perf.get("win_rate", 0.0)
        total_trades = perf.get("total_trades", 0)

        if total_trades < self.min_trades_for_learning:
            if asset_category == "gold":
                default_by_category = ["SignalXAUExtreme", "SignalFibScalp", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            elif asset_category == "crypto":
                default_by_category = ["SignalFibScalp", "SignalSmartMoneyETH", "SignalMomentum", "SignalBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
            else:
                default_by_category = ["SignalEURUSDExtreme", "SignalSmartMoneyEURUSD", "SignalFibScalp", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            filtered = [name for name in default_by_category if name in available]
            if filtered:
                return filtered
            return available

        if available:
            if win_rate > 0.6:
                if asset_category == "gold":
                    preferred = ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
                elif asset_category == "crypto":
                    preferred = ["SignalMomentum", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalBreakout", "SignalBTCStructureBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
                else:
                    preferred = ["SignalEURUSDExtreme", "SignalGBPExtreme", "SignalUSDJPExtreme", "SignalSmartMoneyEURUSD", "SignalMomentum", "SignalBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
            elif win_rate > 0.4:
                if asset_category == "gold":
                    preferred = ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
                elif asset_category == "crypto":
                    preferred = ["SignalMomentum", "SignalBreakout", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
                else:
                    preferred = ["SignalEURUSDExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover", "SignalGBPExtreme", "SignalUSDJPExtreme", "SignalSmartMoneyEURUSD"]
            else:
                if asset_category == "gold":
                    preferred = ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
                elif asset_category == "crypto":
                    preferred = ["SignalMomentum", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalBreakout", "SignalBTCStructureBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
                else:
                    preferred = ["SignalEURUSDExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover", "SignalSmartMoneyEURUSD", "SignalGBPExtreme", "SignalUSDJPExtreme"]
            order = [name for name in preferred if name in available]
            order.extend([name for name in available if name not in order])
            return order

        return ["SignalTrendPullback"]

    def _is_strategy_in_probation(self, symbol_key: str, strategy_name: str) -> bool:
        if not hasattr(self, 'ai') or self.ai is None or not self.ai_enabled:
            return False
        try:
            status = self.ai.strategy_selector.get_probation_status(symbol_key, strategy_name)
            return bool(status.get("in_probation", False))
        except Exception as e:
            logging.error("BRAIN: Error consultando probation para %s/%s: %s", symbol_key, strategy_name, e, exc_info=True)
            return False

    def get_performance_report(self) -> str:
        return self.get_institutional_report()

    def register_current_version(self, version_id: str, name: str, config: dict, description: str = "", set_active: bool = True) -> None:
        self.evaluator.register_version(version_id, name, config, description, set_active=set_active)

    def save_version_report(self, version_id: str, name: str, config: dict, description: str = "", performance: dict = None) -> str:
        report = {
            "version_id": version_id,
            "name": name,
            "description": description,
            "config": config,
            "performance": performance or {},
            "timestamp": datetime.now().isoformat(),
        }
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = f"version_report_{version_id}_{timestamp_str}.json"
        try:
            with open(report_path, 'w', encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logging.info("BRAIN: Reporte de version guardado en %s", report_path)
            return report_path
        except Exception as e:
            logging.error("BRAIN: Error guardando reporte de version: %s", e, exc_info=True)
            return ""
