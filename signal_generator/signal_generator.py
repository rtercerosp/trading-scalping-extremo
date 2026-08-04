from queue import Queue
import logging

import pandas as pd

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from platform_connector.platform_connector import PlatformConnector
from order_executor.order_executor import OrderExecutor
from portfolio.portfolio import Portfolio

from .interfaces.signal_generator_interface import ISignalGenerator
from .properties.signal_generator_properties import (
    BaseSignalProps,
    MACrossoverProps,
    RSIProps,
    TrendPullbackProps,
    SmartMoneySignalProps,
    BollingerBandsProps,
)
from .signals.signal_ma_crossover import SignalMACrossover
from .signals.signal_rsi_mr import SignalRSI
from .signals.signal_trend_pullback import SignalTrendPullback
from .signals.signal_breakout import SignalBreakout
from .signals.signal_momentum import SignalMomentum
from .signals.signal_btc_pullback import SignalBTCPullback
from .signals.signal_eth_pullback import SignalETHPullback
from .signals.signal_btc_structure import SignalBTCStructureBreakout
from .signals.signal_eth_structure import SignalETHStructureBreakout
from .signals.signal_smart_money_eurusd import SignalSmartMoneyEURUSD
from .signals.signal_smart_money_btc import SignalSmartMoneyBTC
from .signals.signal_smart_money_eth import SignalSmartMoneyETH
from .signals.signal_eurusd_extreme import SignalEURUSDExtreme
from .signals.signal_btc_extreme import SignalBTCExtreme
from .signals.signal_candlestick import SignalCandlestickPatterns
from .signals.signal_fib_scalp import SignalFibScalp
from .signals.signal_bollinger_bands import SignalBollingerBands
from utils.utils import Utils
from utils.symbol_utils import CRYPTO_SYMBOLS, FOREX_SYMBOLS, GOLD_SYMBOLS, get_asset_category, normalize_symbol
from utils.dynamic_sr_analyzer import DynamicSRAnalyzer
import config

ASSET_TIMEFRAME_CONFIG = {
    "crypto": {"entry": "15min", "trend": "30min", "rsi": "15min"},
    "gold": {"entry": "15min", "trend": "30min", "rsi": "15min"},
    "forex": {"entry": "5min", "trend": "15min", "rsi": "5min"},
}

ASSET_RISK_CONFIG = {
    "crypto": {"sl_atr_mult": 1.4, "tp_atr_mult": 2.2, "rsi_upper": 72.0, "rsi_lower": 28.0},
    "gold": {"sl_atr_mult": 1.3, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0},
    "forex": {"sl_atr_mult": 1.2, "tp_atr_mult": 2.0, "rsi_upper": 70.0, "rsi_lower": 30.0},
}


class SignalGenerator(ISignalGenerator):
    def __init__(
        self,
        events_queue: Queue,
        data_provider: DataProvider,
        portfolio: Portfolio,
        order_executor: OrderExecutor,
        signal_properties: BaseSignalProps,
        connector: PlatformConnector,
        trading_brain=None,
    ):
        self.events_queue = events_queue
        self.data_provider = data_provider
        self.portfolio = portfolio
        self.order_executor = order_executor
        self.trading_brain = trading_brain
        self.connector = connector

        self.strategies: list[ISignalGenerator] = []
        self.asset_strategies: dict[str, list[ISignalGenerator]] = {}
        self.asset_category_map: dict[str, str] = {}
        self.sr_analyzer = DynamicSRAnalyzer(lookback=50, peak_distance=3, tolerance_pct=0.0015)

        smart_money_props = signal_properties if isinstance(signal_properties, SmartMoneySignalProps) else SmartMoneySignalProps(
            entry_timeframe="5min",
            trend_timeframe="15min",
            trend_fast_period=10,
            trend_slow_period=20,
            ema_fast_period=9,
            ema_slow_period=21,
            rsi_period=14,
            rsi_bull_threshold=52.0,
            rsi_bear_threshold=48.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            fvg_lookback=20,
            fib_lookback=30,
            atr_period=14,
            sl_atr_mult=1.2,
            tp_atr_mult=2.0,
            min_liquidity_gap_points=0.0,
            use_fibonacci=True,
            use_fvg=True,
            use_macd=True,
        )
        self.strategies.append(SignalSmartMoneyEURUSD(properties=smart_money_props, connector=connector))
        self.strategies.append(SignalSmartMoneyBTC(properties=smart_money_props, connector=connector))
        self.strategies.append(SignalSmartMoneyETH(properties=smart_money_props, connector=connector))
        self.strategies.append(SignalBTCExtreme(properties=smart_money_props, connector=connector))
        self.strategies.append(SignalEURUSDExtreme(properties=smart_money_props, connector=connector))

        trend_props = signal_properties if isinstance(signal_properties, TrendPullbackProps) else TrendPullbackProps(
            entry_timeframe="5min",
            trend_timeframe="15min",
            trend_fast_period=50,
            trend_slow_period=200,
            setup_ema_period=50,
            rsi_period=14,
            rsi_bull_threshold=52.0,
            rsi_bear_threshold=48.0,
            atr_period=14,
            sl_atr_mult=1.2,
            tp_atr_mult=2.0,
        )
        self.strategies.append(SignalTrendPullback(properties=trend_props, connector=connector))
        self.strategies.append(SignalBreakout(properties=trend_props, connector=connector))
        self.strategies.append(SignalMomentum(properties=trend_props, connector=connector))
        self.strategies.append(SignalBTCStructureBreakout(properties=trend_props, connector=connector))
        self.strategies.append(SignalETHStructureBreakout(properties=trend_props, connector=connector))

        rsi_props = signal_properties if isinstance(signal_properties, RSIProps) else RSIProps(
            timeframe="5min",
            rsi_period=14,
            rsi_upper=70.0,
            rsi_lower=30.0,
            sl_points=100,
            tp_points=200,
        )
        self.strategies.append(SignalRSI(properties=rsi_props, connector=connector))

        self.strategies.append(SignalMACrossover(properties=MACrossoverProps(
            timeframe="5min",
            fast_period=50,
            slow_period=200,
        ), connector=connector))

        self.strategies.append(SignalCandlestickPatterns(properties=TrendPullbackProps(
            entry_timeframe="5min",
            trend_timeframe="15min",
            trend_fast_period=10,
            trend_slow_period=20,
            setup_ema_period=21,
            rsi_period=14,
            rsi_bull_threshold=52.0,
            rsi_bear_threshold=48.0,
            atr_period=14,
            sl_atr_mult=1.2,
            tp_atr_mult=2.0,
        ), connector=connector))

        self.strategies.append(SignalFibScalp(properties=smart_money_props, connector=connector))

        self.strategies.append(SignalBollingerBands(properties=BollingerBandsProps(
            entry_timeframe="5min",
            bb_period=20,
            bb_std_dev=2.0,
            squeeze_threshold_pct=0.05,
            walk_basis_points=50,
            reversal_exit_std=0.5,
            atr_period=14,
            sl_atr_mult=1.2,
            tp_atr_mult=2.0,
        ), connector=connector))

        self._build_asset_strategy_map()

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        return normalize_symbol(symbol)

    def _build_asset_strategy_map(self) -> None:
        all_strategies = list(self.strategies)

        for strategy in all_strategies:
            strategy_name = strategy.__class__.__name__
            for symbol in CRYPTO_SYMBOLS:
                self.asset_category_map[symbol] = "crypto"
                self.asset_strategies.setdefault(symbol, [])
                if strategy_name not in [s.__class__.__name__ for s in self.asset_strategies.get(symbol, [])]:
                    self.asset_strategies[symbol].append(strategy)
            for symbol in GOLD_SYMBOLS:
                self.asset_category_map[symbol] = "gold"
                self.asset_strategies.setdefault(symbol, [])
                if strategy_name not in [s.__class__.__name__ for s in self.asset_strategies.get(symbol, [])]:
                    self.asset_strategies[symbol].append(strategy)
            for symbol in FOREX_SYMBOLS:
                self.asset_category_map[symbol] = "forex"
                self.asset_strategies.setdefault(symbol, [])
                if strategy_name not in [s.__class__.__name__ for s in self.asset_strategies.get(symbol, [])]:
                    self.asset_strategies[symbol].append(strategy)

        for symbol in CRYPTO_SYMBOLS:
            self.asset_strategies[symbol] = all_strategies
        for symbol in GOLD_SYMBOLS:
            self.asset_strategies[symbol] = all_strategies
        for symbol in FOREX_SYMBOLS:
            self.asset_strategies[symbol] = all_strategies

    def _get_asset_category(self, symbol: str) -> str:
        return get_asset_category(symbol)

    def _get_strategies_for_asset(self, symbol: str) -> list:
        upper = self._normalize_symbol(symbol)
        return self.asset_strategies.get(upper, self.strategies)

    def _evaluate_signal_quality(self, signal_event: SignalEvent, data_event: DataEvent, bars: pd.DataFrame) -> tuple[float, str]:
        if bars.empty or len(bars) < 10:
            return 50.0, "Datos insuficientes para evaluar calidad"

        score = 50.0
        reasons = []

        volume_ratio = bars["vol"].iloc[-1] / bars["vol"].rolling(20).mean().iloc[-1] if bars["vol"].rolling(20).mean().iloc[-1] > 0 else 1.0
        if volume_ratio >= 1.5:
            score += 20.0
            reasons.append(f"volumen {volume_ratio:.1f}x superior a la media")
        elif volume_ratio >= 1.2:
            score += 10.0
            reasons.append(f"volumen {volume_ratio:.1f}x superior a la media")

        bar_range = bars["high"].iloc[-1] - bars["low"].iloc[-1]
        atr = bars["high"].sub(bars["low"]).rolling(14).mean().iloc[-1] if len(bars) >= 14 else bar_range
        if atr > 0 and bar_range >= atr * 1.2:
            score += 15.0
            reasons.append("rango de vela superior al ATR")

        price = signal_event.target_price or bars["close"].iloc[-1]
        fvg_bullish = any(bars["low"].iloc[-i] > bars["high"].iloc[-i - 2] for i in range(1, 4) if len(bars) > i + 2)
        fvg_bearish = any(bars["high"].iloc[-i] < bars["low"].iloc[i - 2] for i in range(1, 4) if len(bars) > i + 2)
        if signal_event.signal == "BUY" and fvg_bullish:
            score += 10.0
            reasons.append("FVG Alcista detectado")
        if signal_event.signal == "SELL" and fvg_bearish:
            score += 10.0
            reasons.append("FVG Bajista detectado")

        fib_zone = None
        if len(bars) >= 20:
            swing_high = bars["high"].iloc[-20:-2].max()
            swing_low = bars["low"].iloc[-20:-2].min()
            if swing_high > swing_low:
                fib_382 = swing_low + (swing_high - swing_low) * 0.382
                fib_618 = swing_low + (swing_high - swing_low) * 0.618
                if fib_382 <= price <= fib_618:
                    score += 10.0
                    fib_zone = f"Fibonacci {fib_382:.5f}-{fib_618:.5f}"
        if fib_zone:
            reasons.append(f"Entrada en zona {fib_zone}")

        try:
            sr_data = self.sr_analyzer.analyze(bars)
            current_price = sr_data.get("current_price")
            if current_price is not None:
                support_levels = sr_data.get("support_levels", [])
                resistance_levels = sr_data.get("resistance_levels", [])
                if signal_event.signal == "BUY":
                    near_support = any(abs(current_price - s["price"]) / max(abs(current_price), 1e-9) < 0.002 for s in support_levels[:3])
                    near_resistance = any(abs(current_price - r["price"]) / max(abs(current_price), 1e-9) < 0.002 for r in resistance_levels[:3])
                    if near_support:
                        score += 10.0
                        reasons.append("Precio cerca de soporte dinámico")
                    if near_resistance:
                        score -= 5.0
                        reasons.append("Precio cerca de resistencia dinámica")
                elif signal_event.signal == "SELL":
                    near_resistance = any(abs(current_price - r["price"]) / max(abs(current_price), 1e-9) < 0.002 for r in resistance_levels[:3])
                    near_support = any(abs(current_price - s["price"]) / max(abs(current_price), 1e-9) < 0.002 for s in support_levels[:3])
                    if near_resistance:
                        score += 10.0
                        reasons.append("Precio cerca de resistencia dinámica")
                    if near_support:
                        score -= 5.0
                        reasons.append("Precio cerca de soporte dinámico")
        except Exception as e:
            logger.debug("SIGNAL GENERATOR: Error evaluando S/R dinámico: %s", e, exc_info=True)

        tp_distance = abs(signal_event.tp - signal_event.target_price) / (bars["close"].iloc[-1] * 0.0001) if signal_event.target_price else abs(signal_event.tp - signal_event.sl) / (bars["close"].iloc[-1] * 0.0001)
        if tp_distance >= 3.0:
            score += 5.0
            reasons.append("TP amplio para scalping")

        justification = "; ".join(reasons) if reasons else "Señal estándar sin catalizadores adicionales"
        return min(score, 100.0), justification

    def _is_signal_viable(self, symbol: str, signal_event: SignalEvent, asset_category: str) -> bool:
        if signal_event is None:
            return False

        try:
            symbol_info = self.connector.get_symbol_info(symbol)
            last_tick = self.data_provider.get_latest_tick(symbol)
            if symbol_info is None or last_tick is None:
                return False

            spread_points = abs(last_tick.get("ask", 0) - last_tick.get("bid", 0)) / symbol_info.point
            atr_points = getattr(signal_event, "atr_points", None)
            if atr_points is None:
                bars = self.data_provider.get_latest_closed_bars(symbol, "5min", 20)
                if not bars.empty and len(bars) >= 14:
                    high_low = bars["high"] - bars["low"]
                    high_close = (bars["high"] - bars["close"].shift(1)).abs()
                    low_close = (bars["low"] - bars["close"].shift(1)).abs()
                    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                    atr = tr.rolling(14).mean().iloc[-1]
                    atr_points = atr / symbol_info.point if atr and atr > 0 else 0
                else:
                    atr_points = 0

            min_stop_points = symbol_info.trade_stops_level + 5
            tp_distance = abs(signal_event.tp - signal_event.target_price) / symbol_info.point if signal_event.target_price else abs(signal_event.tp - signal_event.sl) / symbol_info.point

            if config.STRATEGY_VERSION == "V8_EXTREME_SCALPING":
                tp_threshold = 1.5 if asset_category == "crypto" else 1.2 if asset_category == "gold" else 1.0
                atr_threshold = 2.0 if asset_category == "crypto" else 1.5 if asset_category == "gold" else 1.0
            else:
                if asset_category == "gold":
                    tp_threshold = 2.0
                    atr_threshold = 3.0
                elif asset_category == "crypto":
                    tp_threshold = 0.85
                    atr_threshold = 1.2
                else:
                    tp_threshold = 0.6
                    atr_threshold = 0.8

            if tp_distance > 0 and spread_points > tp_distance * tp_threshold:
                return False

            if atr_points > 0 and spread_points > atr_points * atr_threshold:
                return False

            return True
        except Exception as e:
            logging.error("SIGNAL GENERATOR: Error evaluando viabilidad para %s: %s", symbol, e, exc_info=True)
            return True

    def generate_signal(self, data_event: DataEvent) -> None:
        print(f"{Utils.dateprint()} - SIGNAL GENERATOR: generate_signal para {data_event.symbol}")
        asset_category = self._get_asset_category(data_event.symbol)
        strategies = self._get_strategies_for_asset(data_event.symbol)
        print(f"{Utils.dateprint()} - SIGNAL GENERATOR: asset_category={asset_category}, strategies={[s.__class__.__name__ for s in strategies]}")
        market_regime = "unknown"
        analysis_context = {}

        if self.trading_brain:
            if getattr(self.trading_brain, "ai_enabled", False) and getattr(self.trading_brain, "ai", None) is not None:
                try:
                    bars = self.data_provider.get_latest_closed_bars(data_event.symbol, "15min", 80)
                    market_analysis = self.trading_brain.ai.analyze_market(data_event.symbol, bars)
                    if market_analysis.get("valid"):
                        market_regime = market_analysis.get("regime", "unknown")
                        analysis_context = market_analysis
                except Exception as e:
                    print(f"{Utils.dateprint()} - SIGNAL GENERATOR: Error analizando mercado para {data_event.symbol}: {e}")

            self.trading_brain._current_strategies = strategies

            recommended_names = self.trading_brain.get_strategy_recommendation(data_event.symbol, asset_category)
            preferred_strategies = [s for s in strategies if s.__class__.__name__ in recommended_names]
            if preferred_strategies:
                strategies = preferred_strategies

            adaptive_params = self.trading_brain.get_adaptive_params(data_event.symbol)
            if adaptive_params:
                for strategy in strategies:
                    if hasattr(strategy, "sl_atr_mult"):
                        strategy.sl_atr_mult = adaptive_params.get("sl_atr_mult", strategy.sl_atr_mult)
                    if hasattr(strategy, "tp_atr_mult"):
                        strategy.tp_atr_mult = adaptive_params.get("tp_atr_mult", strategy.tp_atr_mult)

            try:
                timeframes = self.trading_brain.get_asset_timeframes(data_event.symbol)
                risk_overrides = self.trading_brain.get_asset_risk_overrides(data_event.symbol)
                for strategy in strategies:
                    if hasattr(strategy, "set_timeframes"):
                        strategy.set_timeframes(
                            entry_timeframe=timeframes.get("entry", "5min"),
                            trend_timeframe=timeframes.get("trend"),
                            rsi_timeframe=timeframes.get("rsi"),
                        )
                    if hasattr(strategy, "sl_atr_mult") and risk_overrides.get("sl_atr_mult"):
                        strategy.sl_atr_mult = risk_overrides["sl_atr_mult"]
                    if hasattr(strategy, "tp_atr_mult") and risk_overrides.get("tp_atr_mult"):
                        strategy.tp_atr_mult = risk_overrides["tp_atr_mult"]
                    if hasattr(strategy, "rsi_upper") and risk_overrides.get("rsi_upper"):
                        strategy.rsi_upper = risk_overrides["rsi_upper"]
                    if hasattr(strategy, "rsi_lower") and risk_overrides.get("rsi_lower"):
                        strategy.rsi_lower = risk_overrides["rsi_lower"]
            except Exception as e:
                print(f"{Utils.dateprint()} - SIGNAL GENERATOR: Error aplicando timeframes/riesgo por activo: {e}")

        signal_candidates = []
        for strategy in strategies:
            try:
                signal_event = strategy.generate_signal(
                    data_event,
                    self.data_provider,
                    self.portfolio,
                    self.order_executor,
                    asset_category=asset_category,
                )
                if signal_event is not None:
                    if not self._is_signal_viable(data_event.symbol, signal_event, asset_category):
                        print(f"{Utils.dateprint()} - SIGNAL GENERATOR: Señal descartada por spread/volatilidad en {strategy.__class__.__name__} para {data_event.symbol}")
                        continue
                    try:
                        bars = self.data_provider.get_latest_closed_bars(data_event.symbol, "5min", 50)
                        quality_score, justification = self._evaluate_signal_quality(signal_event, data_event, bars)
                        signal_event.quality_score = quality_score
                        signal_event.justification = justification
                    except Exception as quality_error:
                        logging.error("SIGNAL GENERATOR: Error evaluando calidad para %s: %s", data_event.symbol, quality_error, exc_info=True)
                        signal_event.quality_score = 50.0
                        signal_event.justification = "Calidad no evaluada por error"
                    print(f"{Utils.dateprint()} - SIGNAL GENERATOR: Señal generada por {strategy.__class__.__name__}: {signal_event.signal} {data_event.symbol} | calidad={signal_event.quality_score:.1f} | {signal_event.justification}")
                    signal_candidates.append((strategy, signal_event))
                else:
                    print(f"{Utils.dateprint()} - SIGNAL GENERATOR: {strategy.__class__.__name__} no generó señal para {data_event.symbol}")
            except Exception as e:
                print(f"{Utils.dateprint()} - SIGNAL GENERATOR: Error en estrategia {strategy.__class__.__name__}: {e}")

        if not signal_candidates:
            return

        signal_candidates.sort(key=lambda item: item[1].quality_score, reverse=True)

        buy_signals = [(s, se) for s, se in signal_candidates if se.signal == "BUY"]
        sell_signals = [(s, se) for s, se in signal_candidates if se.signal == "SELL"]

        consensus_threshold = 1 if config.STRATEGY_VERSION == "V8_EXTREME_SCALPING" else 2

        if len(buy_signals) >= consensus_threshold and len(buy_signals) >= len(sell_signals):
            strategy, signal_event = buy_signals[0]
            enriched_event = signal_event.copy(update={
                "strategy_name": "+".join([s.__class__.__name__ for s, _ in buy_signals]),
                "asset_category": asset_category,
                "market_regime": market_regime,
                "analysis_context": analysis_context,
                "quality_score": signal_event.quality_score,
                "justification": signal_event.justification,
            })
            logging.info("SIGNAL GENERATOR: Señal BUY final %s calidad=%.1f justificación=%s", signal_event.symbol, signal_event.quality_score, signal_event.justification)
            self.events_queue.put(enriched_event)
        elif len(sell_signals) >= consensus_threshold and len(sell_signals) >= len(buy_signals):
            strategy, signal_event = sell_signals[0]
            enriched_event = signal_event.copy(update={
                "strategy_name": "+".join([s.__class__.__name__ for s, _ in sell_signals]),
                "asset_category": asset_category,
                "market_regime": market_regime,
                "analysis_context": analysis_context,
                "quality_score": signal_event.quality_score,
                "justification": signal_event.justification,
            })
            logging.info("SIGNAL GENERATOR: Señal SELL final %s calidad=%.1f justificación=%s", signal_event.symbol, signal_event.quality_score, signal_event.justification)
            self.events_queue.put(enriched_event)
