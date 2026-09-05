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


RESEARCH_MODE = True


from brain.models import TradeRecord

try:
    from research.research_database import ResearchDatabase
    from research.portfolio_lab import PortfolioLab, PortfolioLabState
    from research.advanced_metrics_engine import AdvancedMetricsEngine
    from research.exit_model_comparator import ExitModelComparator
    from research.ai_self_improvement import AISelfImprovement
    _RESEARCH_AVAILABLE = True
except Exception:
    _RESEARCH_AVAILABLE = False


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
        self._consecutive_losses_by_asset: Dict[str, int] = {}
        self._max_consecutive_losses = 2
        self._daily_loss_pct_limit = 0.01
        self._daily_start_balance = 0.0
        self._circuit_breaker_active = False
        self._circuit_breaker_reason = None
        self._asset_breaker_until: Dict[str, float] = {}
        self._boost_cache: Dict[str, dict] = {}
        self._last_boost_eval_ts: float = 0.0
        self._boost_interval_seconds: int = getattr(config, "ASSET_BOOST_COOLDOWN_SECONDS", 300)
        self.ai_storage_path = os.path.join("ai", getattr(config, "STRATEGY_VERSION", "V14_DIVERSIFIED_RISK_MANAGED").lower())

        try:
            from ai.trading_ai import TradingAI
            self.ai = TradingAI(storage_path=self.ai_storage_path)
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

        if _RESEARCH_AVAILABLE and getattr(config, "RESEARCH_MODE", False):
            self.research_db = ResearchDatabase()
            self.portfolio_lab = PortfolioLab(self.research_db)
            self.metrics_engine = AdvancedMetricsEngine(self.research_db)
            self.exit_comparator = ExitModelComparator(self.research_db)
            self.ai_improvement = AISelfImprovement(self.research_db)
            self._last_research_ts = 0.0
            self._research_interval_seconds = 600
            self._last_known_equity = 0.0
            self._last_mfe: dict[str, float] = {}
            self._last_mae: dict[str, float] = {}
        else:
            self.research_db = None

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

    def _optimize_during_cooldown(self, symbol_key: str) -> None:
        """
        Durante circuit breaker cooldown: busca activamente mejores configuraciones.
        - Recalibra SL/TP multipliers basado en MFE/MAE históricos
        - Prueba estrategias alternativas en shadow mode
        - Ajusta risk_pct según volatilidad reciente
        """
        if not hasattr(self, "_cooldown_optimizations"):
            self._cooldown_optimizations = {}
        
        now_ts = time.time()
        last_opt = self._cooldown_optimizations.get(symbol_key, 0.0)
        # Solo optimizar cada 5 minutos durante cooldown
        if now_ts - last_opt < 300:
            return
        
        self._cooldown_optimizations[symbol_key] = now_ts
        
        try:
            if not getattr(self, "research_db", None):
                return
            
            trades = self.research_db.get_trades(symbol=symbol_key)
            if len(trades) < 20:
                return
            
            # 1. Analyze MFE/MAE para ajustar SL/TP
            mfe_vals = [float(t.get("mfe_points", 0) or 0) for t in trades if t.get("win")]
            mae_vals = [float(t.get("mae_points", 0) or 0) for t in trades if not t.get("win")]
            
            if mfe_vals and mae_vals:
                avg_mfe = sum(mfe_vals) / len(mfe_vals)
                avg_mae = sum(mae_vals) / len(mae_vals)
                
                # Optimal SL ≈ 1.5x avg MAE, TP ≈ 1.5x avg MFE (approx)
                optimal_sl_mult = max(0.5, min(2.0, avg_mae / 100))  # normalize
                optimal_tp_mult = max(1.0, min(4.0, avg_mfe / 100))
                
                import config
                if symbol_key in config.EXTREME_SCALPING_PARAMS:
                    current_sl = config.EXTREME_SCALPING_PARAMS[symbol_key].get("sl_atr_mult", 1.0)
                    current_tp = config.EXTREME_SCALPING_PARAMS[symbol_key].get("tp_atr_mult", 2.0)
                    
                    # Move 20% toward optimal
                    new_sl = current_sl + (optimal_sl_mult - current_sl) * 0.2
                    new_tp = current_tp + (optimal_tp_mult - current_tp) * 0.2
                    
                    if not hasattr(self, "_research_param_overrides"):
                        self._research_param_overrides = {}
                    self._research_param_overrides[f"sl_atr_mult_{symbol_key}"] = round(new_sl, 2)
                    self._research_param_overrides[f"tp_atr_mult_{symbol_key}"] = round(new_tp, 2)
                    
                    logging.info("COOLDOWN OPT: %s SL_mult %.2f->%.2f TP_mult %.2f->%.2f (avg_MFE=%.1f MAE=%.1f)",
                                symbol_key, current_sl, new_sl, current_tp, new_tp, avg_mfe, avg_mae)
            
            # 2. Identify best performing strategy for this symbol
            strategy_perf = {}
            for t in trades:
                strat = t.get("strategy", "UNKNOWN")
                if strat not in strategy_perf:
                    strategy_perf[strat] = {"wins": 0, "losses": 0, "profit": 0.0}
                if t.get("win"):
                    strategy_perf[strat]["wins"] += 1
                else:
                    strategy_perf[strat]["losses"] += 1
                strategy_perf[strat]["profit"] += float(t.get("profit", 0) or 0)
            
            # Find best strategy with min 10 trades
            best_strat = None
            best_score = -999
            for strat, perf in strategy_perf.items():
                total = perf["wins"] + perf["losses"]
                if total >= 10:
                    wr = perf["wins"] / total
                    score = wr * perf["profit"]
                    if score > best_score:
                        best_score = score
                        best_strat = strat
            
            if best_strat:
                # Boost this strategy in recommendations
                if not hasattr(self, "_cooldown_strategy_boost"):
                    self._cooldown_strategy_boost = {}
                self._cooldown_strategy_boost[symbol_key] = best_strat
                logging.info("COOLDOWN OPT: %s best strategy during cooldown = %s (score=%.2f)",
                            symbol_key, best_strat, best_score)
            
            # 3. Adjust risk based on recent volatility
            recent_trades = trades[-20:] if len(trades) >= 20 else trades
            if recent_trades:
                profits = [float(t.get("profit", 0) or 0) for t in recent_trades]
                import statistics
                try:
                    vol = statistics.stdev(profits) if len(profits) > 1 else 0
                    avg_profit = statistics.mean(profits)
                    if avg_profit < 0 and vol > 0:
                        # Losing and volatile -> reduce risk
                        risk_key = f"risk_pct_{symbol_key}"
                        current_risk = getattr(config, "EXTREME_SCALPING_PARAMS", {}).get(symbol_key, {}).get("risk_pct", 0.01)
                        new_risk = max(0.002, current_risk * 0.7)
                        if not hasattr(self, "_research_param_overrides"):
                            self._research_param_overrides = {}
                        self._research_param_overrides[risk_key] = round(new_risk, 4)
                        logging.info("COOLDOWN OPT: %s risk_pct %.4f->%.4f (recent_avg=%.2f vol=%.2f)",
                                    symbol_key, current_risk, new_risk, avg_profit, vol)
                except:
                    pass
                    
        except Exception as e:
            logging.error("BRAIN: Error en cooldown optimization para %s: %s", symbol_key, e, exc_info=True)

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

        # Verificar circuit breaker temporal por activo
        now_ts = time.time()
        asset_breaker_until = self._asset_breaker_until.get(symbol_key, 0.0)
        if asset_breaker_until > now_ts:
            remaining = int((asset_breaker_until - now_ts) / 60)
            
            # Durante cooldown: buscar mejores estrategias/params
            self._optimize_during_cooldown(symbol_key)
            
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"Circuit breaker activo para {symbol_key}. Optimizando params... Reintentar en {remaining} minutos",
            })
            return state

        perf = self.asset_performance.get(symbol_key, {})
        total_trades = perf.get("total_trades", 0)
        consecutive_losses = perf.get("consecutive_losses", 0)
        current_drawdown = perf.get("current_drawdown", 0.0)
        win_rate = perf.get("win_rate", 0.0)

        extreme_params = config.EXTREME_SCALPING_PARAMS.get(symbol_key, {})

        # === CIRCUIT BREAKER POR ACTIVO: DRAWDOWN ===
        if getattr(config, "ASSET_CIRCUIT_BREAKER_ENABLED", True) and total_trades >= getattr(config, "ASSET_MIN_TRADES_FOR_BREAKER", 10):
            if current_drawdown <= getattr(config, "ASSET_DRAWDOWN_EXCLUDE_PCT", -0.20):
                cooldown = getattr(config, "ASSET_BREAKER_COOLDOWN_SECONDS", 7200)
                if current_drawdown <= -0.30:
                    cooldown = 8 * 3600
                elif current_drawdown <= -0.25:
                    cooldown = 4 * 3600
                self._asset_breaker_until[symbol_key] = now_ts + cooldown
                state.update({
                    "tradeable": False,
                    "excluded": True,
                    "reason": f"Drawdown crítico {current_drawdown:.1%} excluye {symbol_key} por {cooldown // 3600}h",
                })
                logging.critical("CIRCUIT BREAKER ACTIVO %s: drawdown %.1f%% (min %.1f%%). Excluido %d minutos.",
                                symbol_key, current_drawdown * 100,
                                getattr(config, "ASSET_DRAWDOWN_EXCLUDE_PCT", -0.20) * 100,
                                cooldown // 60)
                return state

            if current_drawdown <= getattr(config, "ASSET_DRAWDOWN_BREAKER_PCT", -0.15):
                state.update({
                    "tradeable": False,
                    "excluded": True,
                    "reason": f"Drawdown severo {current_drawdown:.1%} en {symbol_key}",
                })
                logging.warning("ACTIVO BLOQUEADO %s: drawdown %.1f%% supera limite %.1f%%",
                               symbol_key, current_drawdown * 100,
                               getattr(config, "ASSET_DRAWDOWN_BREAKER_PCT", -0.15) * 100)
                return state

            if current_drawdown <= getattr(config, "ASSET_DRAWDOWN_WARNING_PCT", -0.08):
                risk_reduce = 0.5
                state.update({
                    "tradeable": True,
                    "risk_override": max(0.002, (extreme_params.get("risk_pct", 0.01) * risk_reduce)),
                    "reason": f"Drawdown warning {current_drawdown:.1%}, riesgo reducido {risk_reduce:.0%}",
                })

        # === CIRCUIT BREAKER POR PÉRDIDAS CONSECUTIVAS POR ACTIVO ===
        max_consec_losses = getattr(config, "ASSET_MAX_CONSECUTIVE_LOSSES", 5)
        asset_consec_losses = perf.get("consecutive_losses", 0)
        if asset_consec_losses >= max_consec_losses and total_trades >= getattr(config, "ASSET_MIN_TRADES_FOR_BREAKER", 10):
            self._asset_breaker_until[symbol_key] = now_ts + getattr(config, "ASSET_BREAKER_COOLDOWN_SECONDS", 3600)
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"{asset_consec_losses} pérdidas consecutivas en {symbol_key}. Excluido {getattr(config, 'ASSET_BREAKER_COOLDOWN_SECONDS', 3600) // 60} minutos",
            })
            logging.warning("CIRCUIT BREAKER %s: %d pérdidas consecutivas. Excluido temporalmente.",
                           symbol_key, asset_consec_losses)
            return state

        # === FILTRO POR WIN RATE ===
        min_wr = extreme_params.get("min_win_rate_for_trading", 0.25)
        exclude_wr = extreme_params.get("exclude_if_win_rate_below", 0.20)

        if win_rate < exclude_wr and total_trades >= 20:
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"win_rate {win_rate:.2f} por debajo del umbral mínimo {exclude_wr:.2f}",
            })
            return state

        if total_trades >= 20 and win_rate < 0.25:
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"win_rate {win_rate:.2f} por debajo de 0.25",
            })
            return state

        if win_rate < min_wr and total_trades >= 20:
            state.update({
                "tradeable": True,
                "risk_override": max(0.002, extreme_params.get("risk_pct", 0.01) * 0.5),
                "reason": f"win_rate {win_rate:.2f} por debajo de {min_wr:.2f}, riesgo reducido al 50%",
            })
            return state

        if win_rate >= 0.60 and total_trades >= 20:
            state.update({
                "tradeable": True,
                "risk_override": min(0.015, extreme_params.get("risk_pct", 0.01) * 1.3),
                "reason": f"win_rate {win_rate:.2f} excelente, riesgo aumentado un 30%",
            })

        # === FILTRO GLOBAL DE WIN RATE ===
        if total_trades >= 20 and win_rate < getattr(config, "ASSET_MIN_WIN_RATE_GLOBAL", 0.40):
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"win_rate global {win_rate:.2f} por debajo de {getattr(config, 'ASSET_MIN_WIN_RATE_GLOBAL', 0.40):.2f}",
            })
            return state

        # === FILTRO POR PROFIT FACTOR ===
        profit_factor = perf.get("profit_factor", 0.0)
        if total_trades >= 20 and profit_factor < 0.80:
            state.update({
                "tradeable": False,
                "excluded": True,
                "reason": f"profit_factor {profit_factor:.2f} por debajo de 0.80",
            })
            return state

        # === BOOST POR MEJOR ACTIVO ===
        if getattr(config, "ASSET_BOOST_ENABLED", True) and state.get("risk_override") is None:
            boost_info = self.get_asset_boost_info(symbol_key)
            if boost_info.get("is_top_performer"):
                max_pos_mult = boost_info.get("max_positions_multiplier", 1.0)
                risk_mult = boost_info.get("risk_multiplier", 1.0)
                base_risk = extreme_params.get("risk_pct", 0.01)
                boosted_risk = min(0.018, base_risk * risk_mult)
                state.update({
                    "tradeable": True,
                    "risk_override": boosted_risk,
                    "reason": f"TOP performer (boost x{risk_mult:.1f})",
                })
                state["boost_info"] = boost_info

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

    def get_top_performing_assets(self, top_n: int | None = None) -> list[str]:
        """
        Devuelve los símbolos con mejor rendimiento, sujetos a umbrales mínimos.
        Solo considera activos en el whitelist de boost.
        """
        if not getattr(config, "ASSET_BOOST_ENABLED", True):
            return []

        whitelist = [normalize_symbol(s) for s in getattr(config, "ASSET_BOOST_WHITELIST", [])]
        if whitelist:
            allowed_keys = set(whitelist)
        else:
            allowed_keys = set(self.asset_performance.keys())

        top_n = top_n or getattr(config, "ASSET_BOOST_TOP_N", 1)
        min_trades = getattr(config, "ASSET_BOOST_MIN_TRADES", 10)
        min_wr = getattr(config, "ASSET_BOOST_MIN_WIN_RATE", 0.55)
        min_profit = getattr(config, "ASSET_BOOST_MIN_PROFIT", 20.0)
        now_ts = time.time()

        if now_ts - self._last_boost_eval_ts < self._boost_interval_seconds and self._boost_cache.get("top_assets"):
            return self._boost_cache.get("top_assets", [])

        candidates = []
        for symbol_key, perf in self.asset_performance.items():
            if symbol_key not in allowed_keys:
                continue
            total_trades = perf.get("total_trades", 0)
            win_rate = perf.get("win_rate", 0.0)
            total_profit = perf.get("total_profit", 0.0)
            if total_trades >= min_trades and win_rate >= min_wr and total_profit >= min_profit:
                candidates.append((symbol_key, total_profit, win_rate, total_trades))

        candidates.sort(key=lambda x: (x[1], x[2], x[3]), reverse=True)
        top_assets = [c[0] for c in candidates[:top_n]]
        self._boost_cache["top_assets"] = top_assets
        self._last_boost_eval_ts = now_ts
        if top_assets:
            logging.info("ASSET BOOST: top performers=%s", top_assets)
        return top_assets

    def get_asset_boost_info(self, symbol: str) -> dict:
        """
        Devuelve información de boost para un activo concreto.
        """
        symbol_key = normalize_symbol(symbol)
        top_assets = self.get_top_performing_assets()
        rank = -1
        for idx, asset in enumerate(top_assets):
            if asset == symbol_key:
                rank = idx
                break
        is_top = rank >= 0
        max_pos_mult = 1.0
        risk_mult = 1.0
        if is_top:
            max_pos_mult = getattr(config, "ASSET_BOOST_MAX_POSITIONS_MULTIPLIER", 1.2) if rank == 0 else 1.1
            risk_mult = getattr(config, "ASSET_BOOST_RISK_MULTIPLIER", 1.15) if rank == 0 else 1.05
        return {
            "is_top_performer": is_top,
            "top_assets": top_assets,
            "max_positions_multiplier": max_pos_mult,
            "risk_multiplier": risk_mult,
        }

    def get_zero_loss_params(self, symbol: str) -> dict:
        """Expone parámetros V10/V11/V12 al BreakEvenManager."""
        strategy_version = getattr(config, "STRATEGY_VERSION", "V10_ZERO_LOSS_SCALPING")
        asset_category = get_asset_category(symbol)

        # Start with V10 defaults as a base
        params = {
            "enabled": getattr(config, "V10_ZERO_LOSS_ENABLED", True),
            "break_even_trigger_pct": getattr(config, "V10_BREAK_EVEN_TRIGGER_PCT", 0.50),
            "break_even_min_trigger_points": getattr(config, "V10_BREAK_EVEN_MIN_TRIGGER_POINTS", {}).get(symbol, 0),
            "break_even_max_trigger_points": getattr(config, "V10_BREAK_EVEN_MAX_TRIGGER_POINTS", {}).get(symbol, 0),
            "break_even_buffer_points": 2,
            "broker_cost_coverage": getattr(config, "V10_BROKER_COST_COVERAGE", {}).get(symbol, {"spread_points": 0, "commission_per_lot": 0.0, "min_profit_points": 0}),
            "reverse_protection_pct": getattr(config, "V10_REVERSE_PROTECTION_PCT", 0.30),
            "gap_protection_pct": getattr(config, "V10_GAP_PROTECTION_PCT", 0.003),
            "pre_breakeven_max_sl_improvement_pct": getattr(config, "V10_PRE_BREAK_EVEN_MAX_SL_IMPROVEMENT_PCT", 0.15),
            "trailing_activation_pct": getattr(config, "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT", 0.003),
            "trailing_offset_points": getattr(config, "V10_TRAILING_AGGRESSIVE_OFFSET_POINTS", {}).get(symbol, 20), # V10 uses points
            "compounding_volume_multiplier": getattr(config, "V10_COMPOUNDING_VOLUME_MULTIPLIER", 2.0),
            "compounding_min_equity": getattr(config, "V10_COMPOUNDING_MIN_EQUITY", 5000.0),
            "spread_max_points_multiplier": getattr(config, "V10_SPREAD_MAX_POINTS_MULTIPLIER", 1.5),
            "min_broker_coverage_points": getattr(config, "V10_MIN_BROKER_COVERAGE_POINTS", 2),
            "max_volume_per_candle_ratio": getattr(config, "V10_MAX_VOLUME_PER_CANDLE_RATIO", 0.05),
        }

        if strategy_version == "V12_UNIVERSAL_AGGRESSIVE" and getattr(config, "V12_UNIVERSAL_AGGRESSIVE_ENABLED", False):
            # V12 applies to gold/forex, and inherits V11 for crypto
            if asset_category == 'crypto' and hasattr(config, "V11_CRYPTO_PARAMS"):
                params.update(config.V11_CRYPTO_PARAMS.get(asset_category, {}))
            elif asset_category in getattr(config, "V12_AGGRESSIVE_PARAMS", {}):
                params.update(config.V12_AGGRESSIVE_PARAMS.get(asset_category, {}))

        elif strategy_version == "V11_CRYPTO_VOLATILITY" and getattr(config, "V11_CRYPTO_VOLATILITY_ENABLED", False):
            if asset_category == 'crypto' and hasattr(config, "V11_CRYPTO_PARAMS"):
                params.update(config.V11_CRYPTO_PARAMS.get(asset_category, {}))

        # If a percentage-based offset is provided by V11/V12, remove the point-based one from V10
        if 'trailing_offset_pct' in params:
            params.pop('trailing_offset_points', None)

        # Aplicar boost si este activo es el top performer
        if getattr(config, "ASSET_BOOST_ENABLED", True):
            top_assets = self.get_top_performing_assets()
            if top_assets and normalize_symbol(symbol) in top_assets:
                params["trailing_activation_pct"] *= getattr(config, "ASSET_BOOST_RISK_MULTIPLIER", 1.3)
                params["reverse_protection_pct"] = min(0.5, params.get("reverse_protection_pct", 0.3) * getattr(config, "ASSET_BOOST_RISK_MULTIPLIER", 1.3))

        # Apply research-driven parameter overrides
        overrides = getattr(self, "_research_param_overrides", {})
        if overrides:
            # V10 params adjusted by research
            if "V10_BREAK_EVEN_TRIGGER_PCT" in overrides:
                params["break_even_trigger_pct"] = overrides["V10_BREAK_EVEN_TRIGGER_PCT"]
            if "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT" in overrides:
                params["trailing_activation_pct"] = overrides["V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT"]
            if "V10_REVERSE_PROTECTION_PCT" in overrides:
                params["reverse_protection_pct"] = overrides["V10_REVERSE_PROTECTION_PCT"]

        return params

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
            strategy=execution_event.primary_strategy_name or execution_event.strategy_type or execution_event.strategy_name,
            deal_ticket=getattr(execution_event, 'deal_ticket', 0),
            position_ticket=getattr(execution_event, 'position_ticket', 0),
        )
        analysis_context = getattr(execution_event, "analysis_context", {}) or {}
        record.session = str(analysis_context.get("session", "unknown") or "unknown")
        record.regime = getattr(execution_event, "market_regime", "unknown") or "unknown"
        record.volatility = float(analysis_context.get("volatility", 0.0) or 0.0)
        record.atr = float(analysis_context.get("atr_points", 0.0) or 0.0)
        record.spread = float(analysis_context.get("spread_points", 0.0) or 0.0)
        record.volume_profile = float(getattr(execution_event, "volume_profile", 0.0) or 0.0)
        record.news_proximity = getattr(execution_event, "news_proximity", "none") or "none"
        record.trend_strength = float(analysis_context.get("higher_tf_strength", 0.0) or 0.0)
        record.momentum = float(analysis_context.get("momentum", 0.0) or 0.0)
        record.liquidity_score = float(getattr(execution_event, "liquidity_score", 0.0) or 0.0)
        record.entry_score = float(getattr(execution_event, "quality_score", 0.0) or 0.0)
        record.exit_score = float(getattr(execution_event, "exit_score", 0.0) or 0.0)
        record.risk = abs(float(execution_event.entry_price) - float(execution_event.initial_sl))
        record.reward = abs(float(execution_event.initial_tp) - float(execution_event.entry_price))
        record.execution_latency_ms = float(getattr(execution_event, "execution_latency_ms", 0.0) or 0.0)
        record.model_used = execution_event.strategy_name or record.strategy or "default"
        record.parameter_set = {
            "consensus_strategy": execution_event.strategy_name or record.strategy,
            "primary_strategy": record.strategy,
            "risk_pct_override": float(getattr(execution_event, "risk_pct_override", 0.0) or 0.0),
            "strategy_version": getattr(config, "STRATEGY_VERSION", ""),
        }
        record.notes = getattr(execution_event, "justification", "") or ""
        self.trade_history_manager.add_trade(record)
        if getattr(self, "research_db", None) is not None:
            try:
                self.research_db.append_trade(record)
            except Exception:
                pass

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
        record.capital_before = getattr(self, "_last_known_equity", 0.0)
        record.capital_after = record.capital_before + profit
        record.win = bool(profit > 0)
        record.mfe_points = float(getattr(self, "_last_mfe", {}).get(symbol, 0.0) or 0.0)
        record.mae_points = float(getattr(self, "_last_mae", {}).get(symbol, 0.0) or 0.0)
        self.trade_history_manager.save()

        symbol_key = self._symbol_key(symbol)
        self._update_asset_performance(symbol, profit)
        self._update_strategy_performance(symbol, strategy, profit)

        if profit < 0:
            self._consecutive_losses += 1
            self._consecutive_losses_by_asset[symbol_key] = self._consecutive_losses_by_asset.get(symbol_key, 0) + 1
        else:
            self._consecutive_losses = 0
            self._consecutive_losses_by_asset[symbol_key] = 0

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

        if getattr(self, "research_db", None) is not None:
            try:
                self.research_db.append_trade(record)
            except Exception:
                pass
            try:
                self._maybe_run_research()
            except Exception:
                pass

    def is_circuit_breaker_active(self) -> tuple[bool, str | None]:
        return self._circuit_breaker_active, self._circuit_breaker_reason

    def get_consecutive_losses(self) -> int:
        """Retorna el número de pérdidas consecutivas globales para circuit breaker externo."""
        return self._consecutive_losses

    def reset_daily_circuit_breaker(self) -> None:
        self._circuit_breaker_active = False
        self._circuit_breaker_reason = None
        self._consecutive_losses = 0
        self._consecutive_losses_by_asset.clear()
        self._asset_breaker_until.clear()
        self._boost_cache.clear()
        account_info = self.connector.get_account_info() if self.connector else None
        self._daily_start_balance = account_info.balance if account_info else 0.0

    def update_research_market_data(self, symbol: str, mfe_points: float, mae_points: float, equity: float) -> None:
        if getattr(self, "research_db", None) is None:
            return
        try:
            self._last_known_equity = float(equity)
            if mfe_points != 0.0 or mae_points != 0.0:
                self._last_mfe[symbol] = float(mfe_points)
                self._last_mae[symbol] = float(mae_points)
        except Exception:
            pass

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

                    try:
                        sl_hit = exit_reason == "SL"
                        tp_hit = exit_reason in ("TP", "TP1", "TP2")
                        self.ai.learn_from_trade(symbol, matching_record.strategy, profit, sl_hit, tp_hit)
                    except Exception as e:
                        logging.error("BRAIN: Error en aprendizaje AI para %s: %s", symbol, e, exc_info=True)

                    if getattr(self, "research_db", None) is not None:
                        try:
                            self.research_db.append_trade(matching_record)
                        except Exception:
                            pass

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

    def get_strategy_metrics(self, symbol: str, strategy: str) -> dict | None:
        """
        Retrieve strategy performance metrics for Kelly Criterion calculation.

        Returns:
            dict with: win_rate, avg_win, avg_loss, total_trades
            or None if insufficient data
        """
        symbol_key = self._symbol_key(symbol)
        strat_perf = self.strategy_performance.get(symbol_key, {}).get(strategy, {})

        if not strat_perf or strat_perf.get("trades", 0) < 10:
            return None

        trades = strat_perf.get("trades", 0)
        wins = strat_perf.get("wins", 0)
        losses = strat_perf.get("losses", 0)
        gross_profit = strat_perf.get("gross_profit", 0.0)
        gross_loss = strat_perf.get("gross_loss", 0.0)

        if wins == 0 or losses == 0:
            return None

        win_rate = wins / trades
        avg_win = gross_profit / wins if wins > 0 else 0.0
        avg_loss = gross_loss / losses if losses > 0 else 0.0

        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "total_trades": trades,
        }

    def get_asset_timeframes(self, symbol: str) -> dict:
        symbol_key = self._symbol_key(symbol)
        asset_category = get_asset_category(symbol_key)
        if symbol_key == "ETHUSD":
            return {"entry": "1min", "trend": "15min", "rsi": "1min"}
        config = {
            "crypto": {"entry": "15min", "trend": "30min", "rsi": "15min"},
            "gold": {"entry": "15min", "trend": "30min", "rsi": "15min"},
            "forex": {"entry": "5min", "trend": "15min", "rsi": "5min"},
        }
        return config.get(asset_category, config["forex"])

    def get_asset_risk_overrides(self, symbol: str) -> dict:
        symbol_key = self._symbol_key(symbol)
        asset_category = get_asset_category(symbol_key)
        if symbol_key == "ETHUSD":
            base = {"sl_atr_mult": 1.2, "tp_atr_mult": 2.5, "rsi_upper": 75.0, "rsi_lower": 25.0}
        else:
            base = {
                "crypto": {"sl_atr_mult": 1.4, "tp_atr_mult": 2.2, "rsi_upper": 72.0, "rsi_lower": 28.0},
                "gold": {"sl_atr_mult": 1.3, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0},
                "forex": {"sl_atr_mult": 1.2, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0},
            }.get(asset_category, {"sl_atr_mult": 1.2, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0})

        # Apply research-driven overrides
        overrides = getattr(self, "_research_param_overrides", {})
        if overrides:
            sl_key = f"sl_atr_mult_{symbol_key}"
            tp_key = f"tp_atr_mult_{symbol_key}"
            if sl_key in overrides:
                base["sl_atr_mult"] = overrides[sl_key]
            if tp_key in overrides:
                base["tp_atr_mult"] = overrides[tp_key]
            # Also apply global risk_pct boost if available
            risk_key = f"risk_pct_{symbol_key}"
            if risk_key in overrides:
                base["risk_pct_override"] = overrides[risk_key]

        return base

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

        # 1. Cooldown strategy boost (found during circuit breaker optimization)
        if hasattr(self, "_cooldown_strategy_boost") and symbol_key in self._cooldown_strategy_boost:
            boosted = self._cooldown_strategy_boost[symbol_key]
            if boosted in available:
                remaining = [name for name in available if name != boosted]
                logging.info("STRAT REC: %s using cooldown-boosted strategy %s", symbol_key, boosted)
                return [boosted] + remaining

        # 2. Configured primary strategies
        configured = getattr(config, "ASSET_PRIMARY_STRATEGIES", {}).get(symbol_key, [])
        configured = [name for name in configured if name in available]
        if configured:
            remaining = [name for name in available if name not in configured]
            return configured + remaining

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

        # Determine result using single return pattern
        result = None
        
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
                result = filtered
            else:
                result = available
        else:
            # Win-rate based strategy selection
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
            result = order
            
            return result
    
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

    def _maybe_run_research(self) -> None:
        if getattr(self, "research_db", None) is None:
            return
        try:
            now = time.time()
            if now - getattr(self, "_last_research_ts", 0.0) < getattr(self, "_research_interval_seconds", 600):
                return
            self._last_research_ts = now
            trades = self.research_db.get_trades()
            if len(trades) < 10:
                return
            metrics = self.metrics_engine.compute(trades)
            exit_rankings = self.exit_comparator.evaluate(trades)
            recommendations = self.ai_improvement.analyze(trades)
            portfolio_state = {
                "open_positions": getattr(self.portfolio, "open_positions", 0),
                "exposure_by_symbol": getattr(self.portfolio, "exposure", {}),
                "return_by_symbol": {k: v for k, v in getattr(self.performance_tracker, "asset_performance", {}).items()},
                "return_by_strategy": {k: v for k, v in getattr(self.performance_tracker, "strategy_performance", {}).items()},
            }
            report = self.metrics_engine.generate_report(trades, metrics, exit_rankings, portfolio_state)
            print(f"{Utils.dateprint()} - BRAIN RESEARCH: Reporte actualizado. Trades={len(trades)}, PF={metrics.profit_factor:.2f}, WR={metrics.win_rate:.2%}")

            # --- APPLY RESEARCH FINDINGS TO LIVE PARAMETERS ---
            self._apply_research_to_params(exit_rankings, recommendations, metrics)
        except Exception as e:
            logging.error("BRAIN: Error en ciclo research: %s", e, exc_info=True)

    def _apply_research_to_params(self, exit_rankings: dict, recommendations: object, metrics: object) -> None:
        """Apply research findings to EXTREME_SCALPING_PARAMS and V10 params in real-time."""
        try:
            import config

            # Initialize research overrides cache
            if not hasattr(self, "_research_param_overrides"):
                self._research_param_overrides = {}

            # 1. Adjust EXTREME_SCALPING_PARAMS per symbol based on exit model performance
            if exit_rankings:
                best_exit_model = max(exit_rankings.items(), key=lambda kv: kv[1].score)[0] if exit_rankings else None
                if best_exit_model and hasattr(exit_rankings[best_exit_model], 'win_rate'):
                    best_wr = exit_rankings[best_exit_model].win_rate
                    best_pf = exit_rankings[best_exit_model].profit_factor
                    best_expectancy = exit_rankings[best_exit_model].expectancy

                    # If best model significantly outperforms, boost its symbol's risk
                    if best_wr > 0.55 and best_pf > 1.3 and best_expectancy > 0:
                        # Find which symbols contributed most to this model
                        model_trades = [t for t in self.research_db.get_trades() if t.get("model_used") == best_exit_model]
                        symbol_perf = {}
                        for t in model_trades:
                            sym = t.get("symbol", "")
                            symbol_perf[sym] = symbol_perf.get(sym, 0.0) + float(t.get("profit", 0.0) or 0.0)
                        top_symbols = sorted(symbol_perf.items(), key=lambda kv: kv[1], reverse=True)[:3]
                        for sym, _ in top_symbols:
                            sym_key = self._symbol_key(sym)
                            if sym_key in config.EXTREME_SCALPING_PARAMS:
                                # Store per-symbol risk boost in overrides
                                current_risk = config.EXTREME_SCALPING_PARAMS[sym_key].get("risk_pct", 0.01)
                                boosted_risk = min(0.025, current_risk * 1.15)
                                self._research_param_overrides[f"risk_pct_{sym_key}"] = boosted_risk
                                logging.info("RESEARCH ADAPT: Boosted risk for %s to %.4f (best model: %s)", sym_key, boosted_risk, best_exit_model)

            # 2. Adjust V10 break-even/trailing params based on exit reason performance
            if recommendations and hasattr(recommendations, 'best_stop_placement'):
                stop_perf = recommendations.best_stop_placement or {}
                # Find best exit reason by avg profit
                best_exit = max(stop_perf.items(), key=lambda kv: kv[1].get("avg_profit", -999))[0] if stop_perf else None
                if best_exit and "BREAK_EVEN" in best_exit.upper():
                    # Break-even exits are profitable -> make BE more aggressive (trigger earlier)
                    current_trigger = getattr(config, "V10_BREAK_EVEN_TRIGGER_PCT", 0.10)
                    new_trigger = max(0.05, current_trigger * 0.9)
                    self._research_param_overrides["V10_BREAK_EVEN_TRIGGER_PCT"] = new_trigger
                    logging.info("RESEARCH ADAPT: V10 BE trigger adjusted to %.2f%% (best exit: %s)", new_trigger * 100, best_exit)
                elif best_exit and "TRAILING" in best_exit.upper():
                    # Trailing exits profitable -> make trailing more aggressive
                    current_activation = getattr(config, "V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT", 0.001)
                    new_activation = min(0.003, current_activation * 1.2)
                    self._research_param_overrides["V10_TRAILING_AGGRESSIVE_ACTIVATION_PCT"] = new_activation
                    logging.info("RESEARCH ADAPT: V10 trailing activation adjusted to %.4f (best exit: %s)", new_activation, best_exit)

            # 3. Adjust reverse protection based on worst mistakes
            if recommendations and hasattr(recommendations, 'worst_recurring_mistakes'):
                worst = recommendations.worst_recurring_mistakes or []
                if worst and "REVERSE" in worst[0].upper():
                    # Reverse protection triggering too often -> widen it
                    current_rev = getattr(config, "V10_REVERSE_PROTECTION_PCT", 0.25)
                    new_rev = min(0.45, current_rev * 1.15)
                    self._research_param_overrides["V10_REVERSE_PROTECTION_PCT"] = new_rev
                    logging.info("RESEARCH ADAPT: V10 reverse protection widened to %.2f%% (worst mistake: %s)", new_rev * 100, worst[0])

            # 4. Adjust per-symbol SL/TP multipliers based on portfolio allocation performance
            if recommendations and hasattr(recommendations, 'best_portfolio_allocation'):
                alloc = recommendations.best_portfolio_allocation or {}
                for sym, profit in alloc.items():
                    sym_key = self._symbol_key(sym)
                    if sym_key in config.EXTREME_SCALPING_PARAMS and profit > 0:
                        # Winning symbol: slightly increase TP multiplier, decrease SL multiplier
                        params = config.EXTREME_SCALPING_PARAMS[sym_key]
                        new_tp_mult = min(3.5, params.get("tp_atr_mult", 2.0) * 1.05)
                        new_sl_mult = max(0.5, params.get("sl_atr_mult", 1.0) * 0.98)
                        self._research_param_overrides[f"tp_atr_mult_{sym_key}"] = new_tp_mult
                        self._research_param_overrides[f"sl_atr_mult_{sym_key}"] = new_sl_mult
                        logging.info("RESEARCH ADAPT: %s TP mult=%.2f SL mult=%.2f (profit=%.2f)", sym_key, new_tp_mult, new_sl_mult, profit)

            # 5. Update internal cache metadata
            self._research_param_overrides["last_update"] = time.time()
            self._research_param_overrides["metrics_snapshot"] = {
                "profit_factor": getattr(metrics, 'profit_factor', 0.0),
                "win_rate": getattr(metrics, 'win_rate', 0.0),
                "expectancy": getattr(metrics, 'expectancy', 0.0),
            }

        except Exception as e:
            logging.error("BRAIN: Error applying research to params: %s", e, exc_info=True)
