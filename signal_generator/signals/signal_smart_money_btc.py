# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from typing import Optional, Literal

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from order_executor.order_executor import OrderExecutor
from portfolio.portfolio import Portfolio
from platform_connector.platform_connector import PlatformConnector

from .signal_smart_money import SignalSmartMoney
from .signal_bollinger_bands import SignalBollingerBands, BollingerBandsProps
from ..properties.signal_generator_properties import SmartMoneySignalProps
from utils.utils import Utils
from utils.symbol_utils import symbol_matches
from utils.dynamic_sr_analyzer import DynamicSRAnalyzer
from src.risk_manager.coinglass_oracle import CoinGlassOracle, create_coinglass_oracle_from_config


class SignalSmartMoneyBTC(SignalSmartMoney):
    """
    Smart Money Concept strategy for BTCUSD enhanced with:
    - Bollinger Bands squeeze/expansion regime detection
    - Spearman Information Coefficient (IC) validation
    - Dynamic SR-based asymmetric SL/TP (institutional order blocks)
    - Target R:R 1:50 to 1:100 via parametric expansion
    """
    
    def __init__(self, properties: SmartMoneySignalProps, connector: PlatformConnector):
        super().__init__(properties, connector)
        self._allowed_symbols = ["BTCUSD", "BTCUSDc"]
        self.min_atr_points = 200
        
        # CoinGlass Oracle for derivatives data and liquidation map
        self.coinglass_oracle = create_coinglass_oracle_from_config()
        
        # Bollinger Bands regime detector
        self.bb_detector = SignalBollingerBands(
            properties=BollingerBandsProps(
                entry_timeframe="5min",
                bb_period=21,
                bb_std_dev=2.2,
                squeeze_threshold_pct=0.06,
                squeeze_lookback=20,
                walk_basis_points=80,
                walk_min_candles=3,
                reversal_exit_std=0.6,
                atr_period=14,
                sl_atr_mult=1.1,
                tp_atr_mult=2.5,
            ),
            connector=connector
        )
        
        # Dynamic SR Analyzer for institutional order blocks
        self.sr_analyzer = DynamicSRAnalyzer(
            lookback=100,
            peak_distance=5,
            prominence_pct=0.002,
            timeframe="5min",
            min_touches=2
        )
        
        # IC validation parameters
        self.ic_lookback = 50
        self.ic_threshold = 0.15  # Minimum Spearman IC for signal validation
        self.signal_history: list[dict] = []  # Track signal outcomes for IC calculation
        
        # Asymmetric R:R targeting
        self.target_rr_min = 50.0   # 1:50 minimum
        self.target_rr_max = 100.0  # 1:100 target
        self.expansion_factor = 2.0  # Parametric expansion multiplier
        
        # Liquidation map integration parameters
        self.use_liquidation_map = True
        self.liq_max_distance_pct = 0.05  # 5% max distance for relevant liquidation clusters
        self.liq_min_volume_threshold = 50_000_000  # Minimum volume for significant cluster
        
        # Minimum SL distance as % of price (prevents too-tight stops)
        self.min_sl_distance_pct = 0.0015  # 0.15% minimum

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        super().set_timeframes(entry_timeframe, trend_timeframe, rsi_timeframe)
        self._allowed_symbols = ["BTCUSD", "BTCUSDc"]
        # Update BB detector timeframe
        if hasattr(self, 'bb_detector'):
            self.bb_detector.entry_timeframe = entry_timeframe

    def _calculate_spearman_ic(self, bars: pd.DataFrame) -> float:
        """
        Calculate Spearman Information Coefficient between predicted direction and actual returns.
        
        Uses recent signal features vs forward returns to validate predictive power.
        Returns IC in [-1, 1], higher = better predictive signal.
        """
        if len(bars) < self.ic_lookback + 10:
            return 0.0
        
        try:
            # Features: RSI, MACD, BB bandwidth, volume, FVG presence
            close = bars["close"]
            high = bars["high"]
            low = bars["low"]
            volume = bars.get("volume", pd.Series([1]*len(bars), index=bars.index))
            
            # Feature engineering
            rsi = self._rsi(close, 14)
            macd_line, signal_line, _ = self._macd(close, 12, 26, 9)
            macd_signal = macd_line - signal_line
            
            # Bollinger Bands features
            middle, upper, lower, bandwidth = self.bb_detector._bollinger_bands(close, 21, 2.2)
            bb_position = (close - lower) / (upper - lower).replace(0, np.nan)
            
            # FVG presence (binary)
            fvg_bullish = (low.shift(2) > high.shift(4)).astype(float)
            fvg_bearish = (high.shift(2) < low.shift(4)).astype(float)
            fvg_signal = fvg_bullish - fvg_bearish
            
            # Forward returns (next 5 bars)
            forward_ret = close.shift(-5) / close - 1
            
            # Align data
            features = pd.DataFrame({
                "rsi": rsi,
                "macd": macd_signal,
                "bb_pos": bb_position,
                "bb_width": bandwidth,
                "vol": volume / volume.rolling(20).mean(),
                "fvg": fvg_signal
            }).iloc[-self.ic_lookback-5:-5]
            
            targets = forward_ret.iloc[-self.ic_lookback-5:-5]
            
            # Drop NaN
            valid = features.notna().all(axis=1) & targets.notna()
            if valid.sum() < 20:
                return 0.0
            
            features_clean = features[valid]
            targets_clean = targets[valid]
            
            # Calculate IC for each feature, take max absolute
            ics = []
            for col in features_clean.columns:
                if features_clean[col].nunique() > 1:
                    ic, _ = spearmanr(features_clean[col], targets_clean)
                    if not np.isnan(ic):
                        ics.append(abs(ic))
            
            return max(ics) if ics else 0.0
        except Exception as e:
            print(f"{Utils.dateprint()} - SMART BTC: IC calculation error: {e}")
            return 0.0

    def _get_dynamic_sr_levels(self, symbol: str, entry_bars: pd.DataFrame, signal_type: str) -> dict:
        """
        Get dynamic support/resistance levels using DynamicSRAnalyzer.
        Returns institutional order block levels for asymmetric SL/TP placement.
        """
        try:
            sr_data = self.sr_analyzer.analyze(entry_bars)
            current_price = sr_data.get("current_price")
            support_levels = sr_data.get("support_levels", [])
            resistance_levels = sr_data.get("resistance_levels", [])
            
            if current_price is None:
                return {}
            
            # Find nearest institutional levels
            nearest_support = None
            nearest_resistance = None
            
            for level in support_levels:
                if level["price"] < current_price:
                    nearest_support = level
                    break
            
            for level in resistance_levels:
                if level["price"] > current_price:
                    nearest_resistance = level
                    break
            
            # Also check order blocks from parent class
            order_block = self._detect_order_block(entry_bars)
            
            return {
                "current_price": current_price,
                "nearest_support": nearest_support,
                "nearest_resistance": nearest_resistance,
                "order_block": order_block,
                "support_levels": support_levels[:3],
                "resistance_levels": resistance_levels[:3],
            }
        except Exception as e:
            print(f"{Utils.dateprint()} - SMART BTC: Dynamic SR error: {e}")
            return {}

    def _get_liquidation_zones(self, symbol: str, current_price: float) -> dict:
        """
        Get liquidation map zones from CoinGlass Oracle.
        Returns long/short liquidation clusters near current price.
        """
        if not self.use_liquidation_map or not self.coinglass_oracle:
            return {
                "long_liquidation_zones": [],
                "short_liquidation_zones": [],
                "nearest_long_liq": None,
                "nearest_short_liq": None,
            }
        
        try:
            liq_data = self.coinglass_oracle.get_liquidation_zones(
                symbol, 
                current_price, 
                max_distance_pct=self.liq_max_distance_pct
            )
            
            # Filter by minimum volume threshold
            long_zones = [z for z in liq_data.get("long_liquidation_zones", []) 
                         if z.get("volume", 0) >= self.liq_min_volume_threshold]
            short_zones = [z for z in liq_data.get("short_liquidation_zones", []) 
                          if z.get("volume", 0) >= self.liq_min_volume_threshold]
            
            return {
                "long_liquidation_zones": long_zones[:5],
                "short_liquidation_zones": short_zones[:5],
                "nearest_long_liq": long_zones[0] if long_zones else None,
                "nearest_short_liq": short_zones[0] if short_zones else None,
                "total_long_liq_volume": liq_data.get("total_long_liq_volume", 0),
                "total_short_liq_volume": liq_data.get("total_short_liq_volume", 0),
            }
        except Exception as e:
            print(f"{Utils.dateprint()} - SMART BTC: Liquidation zones error: {e}")
            return {
                "long_liquidation_zones": [],
                "short_liquidation_zones": [],
                "nearest_long_liq": None,
                "nearest_short_liq": None,
            }

    def _calculate_asymmetric_sl_tp(
        self,
        entry_price: float,
        signal_type: str,
        sr_levels: dict,
        atr_points: float,
        symbol_info,
        symbol: str
    ) -> tuple:
        """
        Calculate asymmetric SL/TP targeting R:R 50-100 with liquidation map integration.
        
        SL: 1 tick below/above institutional order block coinciding with liquidation cluster
        TP: Parametric expansion toward next major liquidity pool
        """
        point = symbol_info.point
        min_stop_points = symbol_info.trade_stops_level + 5
        current_price = sr_levels.get("current_price", entry_price)
        
        # Minimum SL distance in price terms
        min_sl_distance_price = entry_price * self.min_sl_distance_pct
        min_sl_distance_points = min_sl_distance_price / point
        
        # Get liquidation zones for confluence
        liq_zones = self._get_liquidation_zones(symbol, current_price)
        
        if signal_type == "BUY":
            # SL: Just below nearest support/order block WITH liquidation confluence
            sl_level = None
            sl_source = "none"
            
            # Priority 1: Order block coinciding with long liquidation cluster (institutional mitigation zone)
            ob = sr_levels.get("order_block", {})
            if ob.get("bull_order_block") and ob.get("bull_ob_price", 0) > 0:
                ob_price = ob["bull_ob_price"]
                # Check for liquidation confluence near order block
                for liq in liq_zones.get("long_liquidation_zones", []):
                    if abs(liq["price"] - ob_price) / ob_price < 0.002:  # Within 0.2%
                        sl_level = ob_price
                        sl_source = "order_block_liq_confluence"
                        break
                if sl_level is None:
                    sl_level = ob_price
                    sl_source = "order_block"
            
            # Priority 2: Nearest support with touches >= 2 AND long liquidation cluster
            if sl_level is None and sr_levels.get("nearest_support") and sr_levels["nearest_support"].get("touches", 0) >= 2:
                support_price = sr_levels["nearest_support"]["price"]
                for liq in liq_zones.get("long_liquidation_zones", []):
                    if abs(liq["price"] - support_price) / support_price < 0.003:
                        sl_level = support_price
                        sl_source = "support_liq_confluence"
                        break
                if sl_level is None:
                    sl_level = support_price
                    sl_source = "support"
            
            # Priority 3: Nearest long liquidation cluster (institutional mitigation)
            if sl_level is None and liq_zones.get("nearest_long_liq"):
                sl_level = liq_zones["nearest_long_liq"]["price"]
                sl_source = "liquidation_cluster"
            
            # Priority 4: Any support
            if sl_level is None and sr_levels.get("nearest_support"):
                sl_level = sr_levels["nearest_support"]["price"]
                sl_source = "support_fallback"
            
            if sl_level is not None:
                # SL = 1 tick below support (for BUY)
                sl_price = sl_level - point
                # Ensure minimum distance
                min_sl_dist = max(min_stop_points * point, atr_points * 0.8 * point, min_sl_distance_price)
                if entry_price - sl_price < min_sl_dist:
                    sl_price = entry_price - min_sl_dist
            else:
                # Fallback to ATR-based
                sl_price = entry_price - max(self.sl_atr_mult * atr_points * point, min_stop_points * point, min_sl_distance_price)
                sl_source = "atr_fallback"
            
            # TP: Expand toward next major liquidity pool (short liquidation cluster or resistance)
            risk_dist = entry_price - sl_price
            if risk_dist > 0:
                # Find target: next short liquidation cluster or resistance level
                tp_target_price = None
                tp_source = "none"
                
                # Check short liquidation clusters above entry
                for liq in liq_zones.get("short_liquidation_zones", []):
                    if liq["price"] > entry_price:
                        tp_target_price = liq["price"]
                        tp_source = "short_liquidation_cluster"
                        break
                
                # Fallback to resistance levels
                if tp_target_price is None:
                    for level in sr_levels.get("resistance_levels", []):
                        if level["price"] > entry_price:
                            tp_target_price = level["price"]
                            tp_source = "resistance"
                            break
                
                if tp_target_price:
                    # TP at the liquidity pool
                    tp_distance = tp_target_price - entry_price
                    # Ensure minimum R:R of 50
                    min_tp_dist = risk_dist * self.target_rr_min
                    if tp_distance < min_tp_dist:
                        tp_distance = min_tp_dist
                        tp_source += "_extended"
                    
                    # Cap at reasonable maximum (10% of price)
                    max_tp_dist = entry_price * 0.1
                    tp_distance = min(tp_distance, max_tp_dist)
                    tp_price = entry_price + tp_distance
                else:
                    # Parametric expansion for extreme R:R
                    target_rr = np.random.uniform(self.target_rr_min, self.target_rr_max)
                    tp_distance = risk_dist * target_rr * self.expansion_factor
                    max_tp_dist = entry_price * 0.1
                    tp_distance = min(tp_distance, max_tp_dist)
                    tp_price = entry_price + tp_distance
                    tp_source = "parametric"
                
                # TP1 at 0.5R, TP2 at 1.0R for partial scaling
                tp1_price = entry_price + risk_dist * 0.5
                tp2_price = entry_price + risk_dist * 1.0
            else:
                tp_price = entry_price + atr_points * self.tp_atr_mult * point
                tp1_price = entry_price + atr_points * 0.5 * point
                tp2_price = tp_price
                tp_source = "atr_fallback"
            
            print(f"{Utils.dateprint()} - SMART BTC: LONG SL/TP - SL_Source={sl_source}, TP_Source={tp_source}, "
                  f"Risk={risk_dist/point:.1f}pts, R:R={(tp_price-entry_price)/risk_dist:.1f}")
        
        else:  # SELL
            # SL: Just above nearest resistance/order block WITH liquidation confluence
            sl_level = None
            sl_source = "none"
            
            # Priority 1: Order block coinciding with short liquidation cluster
            ob = sr_levels.get("order_block", {})
            if ob.get("bear_order_block") and ob.get("bear_ob_price", 0) > 0:
                ob_price = ob["bear_ob_price"]
                for liq in liq_zones.get("short_liquidation_zones", []):
                    if abs(liq["price"] - ob_price) / ob_price < 0.002:
                        sl_level = ob_price
                        sl_source = "order_block_liq_confluence"
                        break
                if sl_level is None:
                    sl_level = ob_price
                    sl_source = "order_block"
            
            # Priority 2: Nearest resistance with touches >= 2 AND short liquidation cluster
            if sl_level is None and sr_levels.get("nearest_resistance") and sr_levels["nearest_resistance"].get("touches", 0) >= 2:
                resistance_price = sr_levels["nearest_resistance"]["price"]
                for liq in liq_zones.get("short_liquidation_zones", []):
                    if abs(liq["price"] - resistance_price) / resistance_price < 0.003:
                        sl_level = resistance_price
                        sl_source = "resistance_liq_confluence"
                        break
                if sl_level is None:
                    sl_level = resistance_price
                    sl_source = "resistance"
            
            # Priority 3: Nearest short liquidation cluster
            if sl_level is None and liq_zones.get("nearest_short_liq"):
                sl_level = liq_zones["nearest_short_liq"]["price"]
                sl_source = "liquidation_cluster"
            
            # Priority 4: Any resistance
            if sl_level is None and sr_levels.get("nearest_resistance"):
                sl_level = sr_levels["nearest_resistance"]["price"]
                sl_source = "resistance_fallback"
            
            if sl_level is not None:
                # SL = 1 tick above resistance (for SELL)
                sl_price = sl_level + point
                min_sl_dist = max(min_stop_points * point, atr_points * 0.8 * point, min_sl_distance_price)
                if sl_price - entry_price < min_sl_dist:
                    sl_price = entry_price + min_sl_dist
            else:
                sl_price = entry_price + max(self.sl_atr_mult * atr_points * point, min_stop_points * point, min_sl_distance_price)
                sl_source = "atr_fallback"
            
            # TP: Expand toward next major liquidity pool (long liquidation cluster or support)
            risk_dist = sl_price - entry_price
            if risk_dist > 0:
                tp_target_price = None
                tp_source = "none"
                
                # Check long liquidation clusters below entry
                for liq in liq_zones.get("long_liquidation_zones", []):
                    if liq["price"] < entry_price:
                        tp_target_price = liq["price"]
                        tp_source = "long_liquidation_cluster"
                        break
                
                # Fallback to support levels
                if tp_target_price is None:
                    for level in sr_levels.get("support_levels", []):
                        if level["price"] < entry_price:
                            tp_target_price = level["price"]
                            tp_source = "support"
                            break
                
                if tp_target_price:
                    tp_distance = entry_price - tp_target_price
                    min_tp_dist = risk_dist * self.target_rr_min
                    if tp_distance < min_tp_dist:
                        tp_distance = min_tp_dist
                        tp_source += "_extended"
                    
                    max_tp_dist = entry_price * 0.1
                    tp_distance = min(tp_distance, max_tp_dist)
                    tp_price = entry_price - tp_distance
                else:
                    target_rr = np.random.uniform(self.target_rr_min, self.target_rr_max)
                    tp_distance = risk_dist * target_rr * self.expansion_factor
                    max_tp_dist = entry_price * 0.1
                    tp_distance = min(tp_distance, max_tp_dist)
                    tp_price = entry_price - tp_distance
                    tp_source = "parametric"
                
                tp1_price = entry_price - risk_dist * 0.5
                tp2_price = entry_price - risk_dist * 1.0
            else:
                tp_price = entry_price - atr_points * self.tp_atr_mult * point
                tp1_price = entry_price - atr_points * 0.5 * point
                tp2_price = tp_price
                tp_source = "atr_fallback"
            
            print(f"{Utils.dateprint()} - SMART BTC: SHORT SL/TP - SL_Source={sl_source}, TP_Source={tp_source}, "
                  f"Risk={risk_dist/point:.1f}pts, R:R={(entry_price-tp_price)/risk_dist:.1f}")
        
        return sl_price, tp_price, tp1_price, tp2_price

    def _record_signal_outcome(self, signal_data: dict) -> None:
        """Record signal for IC calculation."""
        self.signal_history.append(signal_data)
        if len(self.signal_history) > 200:
            self.signal_history = self.signal_history[-200:]

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "crypto") -> SignalEvent | None:
        symbol = data_event.symbol
        if not symbol_matches(symbol, self._allowed_symbols):
            return None

        trend_bars = self._load_bars(symbol, self.trend_timeframe, self.trend_slow_period + 30, data_provider)
        entry_bars = self._load_bars(symbol, self.entry_timeframe, max(self.ema_fast_period, self.ema_slow_period, self.rsi_period, self.fvg_lookback, self.fib_lookback) + 50, data_provider)
        if trend_bars.empty or entry_bars.empty or len(entry_bars) < max(self.ema_fast_period, self.ema_slow_period, self.rsi_period) + 10:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        trend_close = trend_bars["close"]
        trend_fast = self._ema(trend_close, self.trend_fast_period)
        trend_slow = self._ema(trend_close, self.trend_slow_period)
        trend_is_bullish = trend_close.iloc[-1] > trend_fast.iloc[-1] > trend_slow.iloc[-1]
        trend_is_bearish = trend_close.iloc[-1] < trend_fast.iloc[-1] < trend_slow.iloc[-1]
        if not trend_is_bullish and not trend_is_bearish:
            return None

        entry_close = entry_bars["close"]
        ema_fast = self._ema(entry_close, self.ema_fast_period)
        ema_slow = self._ema(entry_close, self.ema_slow_period)
        rsi_series = self._rsi(entry_close, self.rsi_period)
        macd_line, signal_line, histogram = self._macd(entry_close, self.macd_fast, self.macd_slow, self.macd_signal)
        atr_series = self._atr(entry_bars, self.atr_period)

        current_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]
        current_macd = macd_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        current_signal = signal_line.iloc[-1]
        current_atr = atr_series.iloc[-1]

        if pd.isna(current_rsi) or pd.isna(prev_rsi) or pd.isna(current_atr) or current_atr <= 0:
            return None

        # ===== BOLLINGER BANDS REGIME DETECTION =====
        bb_regime = self.bb_detector._detect_volatility_regime(
            *self.bb_detector._bollinger_bands(entry_close, self.bb_detector.bb_period, self.bb_detector.bb_std_dev)
        )
        
        # Only trade SQUEEZE breakouts and WALK trends for extreme R:R
        if bb_regime not in ("squeeze", "walk"):
            return None
        
        # ===== SPEARMAN IC VALIDATION =====
        ic_score = self._calculate_spearman_ic(entry_bars)
        if ic_score < self.ic_threshold:
            print(f"{Utils.dateprint()} - SMART BTC: IC={ic_score:.3f} below threshold {self.ic_threshold}, skipping")
            return None
        
        print(f"{Utils.dateprint()} - SMART BTC: Regime={bb_regime}, IC={ic_score:.3f} ✓")

        liquidity = self._detect_liquidity_sweeps(entry_bars, lookback=20)
        smart_money = self._detect_smart_money_bos(entry_bars, period=5)
        order_block = self._detect_order_block(entry_bars)
        fvgs = self._detect_fvg(entry_bars, self.fvg_lookback) if self.use_fvg else []

        fib_levels = {}
        if self.use_fibonacci and len(entry_bars) >= self.fib_lookback:
            swing_high = entry_bars["high"].iloc[-self.fib_lookback:-1].max()
            swing_low = entry_bars["low"].iloc[-self.fib_lookback:-1].min()
            fib_levels = self._compute_fibonacci_levels(swing_high, swing_low)

        ask_price = last_tick.get("ask")
        bid_price = last_tick.get("bid")
        if ask_price is None or bid_price is None:
            return None

        min_stop_points = symbol_info.trade_stops_level + 5
        atr_points = current_atr / symbol_info.point
        if atr_points < getattr(self, 'min_atr_points', 200):
            return None

        spread_points = self._get_spread_points(symbol_info, last_tick)
        
        # ===== DYNAMIC SR LEVELS FOR ASYMMETRIC SL/TP =====
        sr_levels = self._get_dynamic_sr_levels(symbol, entry_bars, "BUY" if trend_is_bullish else "SELL")
        
        bull_fvg_ok = any(f["type"] == "bullish" and f["bottom"] < ask_price for f in fvgs) if self.use_fvg else True
        bear_fvg_ok = any(f["type"] == "bearish" and f["top"] > bid_price for f in fvgs) if self.use_fvg else True
        bull_fib_ok = self._is_price_at_fibonacci_support(ask_price, fib_levels) if self.use_fibonacci and fib_levels else True
        bear_fib_ok = self._is_price_at_fibonacci_resistance(bid_price, fib_levels) if self.use_fibonacci and fib_levels else True
        bull_macd_ok = current_macd > current_signal and current_macd > prev_macd if self.use_macd else True
        bear_macd_ok = current_macd < current_signal and current_macd < prev_macd if self.use_macd else True

        long_trigger = (
            trend_is_bullish
            and bb_regime in ("squeeze", "walk")
            and ask_price > ema_fast.iloc[-1]
            and ema_fast.iloc[-1] > ema_slow.iloc[-1]
            and current_rsi >= self.rsi_bull_threshold
            and current_rsi > prev_rsi
            and bull_macd_ok
            and (smart_money["bos_bullish"] or order_block["bull_order_block"] or liquidity["bullish_sweep"])
            and bull_fvg_ok
            and bull_fib_ok
        )

        short_trigger = (
            trend_is_bearish
            and bb_regime in ("squeeze", "walk")
            and bid_price < ema_fast.iloc[-1]
            and ema_fast.iloc[-1] < ema_slow.iloc[-1]
            and current_rsi <= self.rsi_bear_threshold
            and current_rsi < prev_rsi
            and bear_macd_ok
            and (smart_money["bos_bearish"] or order_block["bear_order_block"] or liquidity["bearish_sweep"])
            and bear_fvg_ok
            and bear_fib_ok
        )

        if long_trigger:
            # Use asymmetric SL/TP targeting extreme R:R
            sl_price, tp_price, tp1_price, tp2_price = self._calculate_asymmetric_sl_tp(
                ask_price, "BUY", sr_levels, atr_points, symbol_info, symbol
            )
            
            print(f"{Utils.dateprint()} - SMART BTC: LONG rsi={current_rsi:.2f} macd={current_macd:.5f} atr={atr_points:.2f} "
                  f"regime={bb_regime} IC={ic_score:.3f} SL={sl_price:.2f} TP={tp_price:.2f} "
                  f"R:R={(tp_price-ask_price)/(ask_price-sl_price):.1f}")
            
            signal_event = SignalEvent(
                symbol=symbol,
                signal="BUY",
                target_order="MARKET",
                target_price=0.0,
                magic_number=portfolio.magic,
                sl=sl_price,
                tp=tp_price,
                tp1=tp1_price,
                tp2=tp2_price,
            )
            
            # Record for IC tracking
            self._record_signal_outcome({
                "symbol": symbol,
                "signal": "BUY",
                "entry": ask_price,
                "sl": sl_price,
                "tp": tp_price,
                "ic": ic_score,
                "regime": bb_regime,
                "sr_levels": sr_levels,
                "timestamp": Utils.dateprint()
            })
            
            return signal_event

        if short_trigger:
            sl_price, tp_price, tp1_price, tp2_price = self._calculate_asymmetric_sl_tp(
                bid_price, "SELL", sr_levels, atr_points, symbol_info, symbol
            )
            
            print(f"{Utils.dateprint()} - SMART BTC: SHORT rsi={current_rsi:.2f} macd={current_macd:.5f} atr={atr_points:.2f} "
                  f"regime={bb_regime} IC={ic_score:.3f} SL={sl_price:.2f} TP={tp_price:.2f} "
                  f"R:R={(bid_price-tp_price)/(sl_price-bid_price):.1f}")
            
            signal_event = SignalEvent(
                symbol=symbol,
                signal="SELL",
                target_order="MARKET",
                target_price=0.0,
                magic_number=portfolio.magic,
                sl=sl_price,
                tp=tp_price,
                tp1=tp1_price,
                tp2=tp2_price,
            )
            
            self._record_signal_outcome({
                "symbol": symbol,
                "signal": "SELL",
                "entry": bid_price,
                "sl": sl_price,
                "tp": tp_price,
                "ic": ic_score,
                "regime": bb_regime,
                "sr_levels": sr_levels,
                "timestamp": Utils.dateprint()
            })
            
            return signal_event

        return None
