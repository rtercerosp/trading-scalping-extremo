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


class SignalSmartMoneyETH(SignalSmartMoney):
    def __init__(self, properties: SmartMoneySignalProps, connector: PlatformConnector):
        super().__init__(properties, connector)
        self._allowed_symbols = ["ETHUSD", "ETHUSDc"]
        self.min_atr_points = 150  # Increased from 20 to prevent micro-ATR trades
        
        # CoinGlass Oracle for derivatives data and liquidation map
        self.coinglass_oracle = create_coinglass_oracle_from_config()
        
        # Dynamic SR Analyzer for institutional order blocks
        self.sr_analyzer = DynamicSRAnalyzer(
            lookback=100,
            peak_distance=5,
            prominence_pct=0.002,
            timeframe="5min",
            min_touches=2
        )
        
        # Asymmetric R:R targeting
        self.target_rr_min = 50.0   # 1:50 minimum
        self.target_rr_max = 100.0  # 1:100 target
        self.expansion_factor = 2.0  # Parametric expansion multiplier
        
        # Liquidation map integration parameters
        self.use_liquidation_map = True
        self.liq_max_distance_pct = 0.05  # 5% max distance for relevant liquidation clusters
        self.liq_min_volume_threshold = 30_000_000  # Minimum volume for significant cluster (ETH lower than BTC)
        
        # Minimum SL distance as % of price (prevents too-tight stops)
        self.min_sl_distance_pct = 0.0015  # 0.15% minimum

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        super().set_timeframes(entry_timeframe, trend_timeframe, rsi_timeframe)
        self._allowed_symbols = ["ETHUSD", "ETHUSDc"]

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
            print(f"{Utils.dateprint()} - SMART ETH: Dynamic SR error: {e}")
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
            print(f"{Utils.dateprint()} - SMART ETH: Liquidation zones error: {e}")
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
        
        liq_zones = self._get_liquidation_zones(symbol, current_price)
        
        # Minimum SL distance in price terms
        min_sl_distance_price = entry_price * self.min_sl_distance_pct
        min_sl_distance_points = min_sl_distance_price / point
        
        if signal_type == "BUY":
            sl_level = None
            sl_source = "none"
            
            ob = sr_levels.get("order_block", {})
            if ob.get("bull_order_block") and ob.get("bull_ob_price", 0) > 0:
                ob_price = ob["bull_ob_price"]
                for liq in liq_zones.get("long_liquidation_zones", []):
                    if abs(liq["price"] - ob_price) / ob_price < 0.002:
                        sl_level = ob_price
                        sl_source = "order_block_liq_confluence"
                        break
                if sl_level is None:
                    sl_level = ob_price
                    sl_source = "order_block"
            
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
            
            if sl_level is None and liq_zones.get("nearest_long_liq"):
                sl_level = liq_zones["nearest_long_liq"]["price"]
                sl_source = "liquidation_cluster"
            
            if sl_level is None and sr_levels.get("nearest_support"):
                sl_level = sr_levels["nearest_support"]["price"]
                sl_source = "support_fallback"
            
            if sl_level is not None:
                # SL = 1 tick below support (for BUY)
                sl_price = sl_level - point
                # Ensure minimum distance from entry
                min_sl_dist = max(min_stop_points * point, atr_points * 0.8 * point, min_sl_distance_price)
                if entry_price - sl_price < min_sl_dist:
                    sl_price = entry_price - min_sl_dist
            else:
                sl_price = entry_price - max(self.sl_atr_mult * atr_points * point, min_stop_points * point, min_sl_distance_price)
                sl_source = "atr_fallback"
            
            risk_dist = entry_price - sl_price
            if risk_dist > 0:
                tp_target_price = None
                tp_source = "none"
                
                for liq in liq_zones.get("short_liquidation_zones", []):
                    if liq["price"] > entry_price:
                        tp_target_price = liq["price"]
                        tp_source = "short_liquidation_cluster"
                        break
                
                if tp_target_price is None:
                    for level in sr_levels.get("resistance_levels", []):
                        if level["price"] > entry_price:
                            tp_target_price = level["price"]
                            tp_source = "resistance"
                            break
                
                if tp_target_price:
                    tp_distance = tp_target_price - entry_price
                    min_tp_dist = risk_dist * self.target_rr_min
                    if tp_distance < min_tp_dist:
                        tp_distance = min_tp_dist
                        tp_source += "_extended"
                    
                    max_tp_dist = entry_price * 0.1
                    tp_distance = min(tp_distance, max_tp_dist)
                    tp_price = entry_price + tp_distance
                else:
                    target_rr = np.random.uniform(self.target_rr_min, self.target_rr_max)
                    tp_distance = risk_dist * target_rr * self.expansion_factor
                    max_tp_dist = entry_price * 0.1
                    tp_distance = min(tp_distance, max_tp_dist)
                    tp_price = entry_price + tp_distance
                    tp_source = "parametric"
                
                tp1_price = entry_price + risk_dist * 0.5
                tp2_price = entry_price + risk_dist * 1.0
            else:
                tp_price = entry_price + atr_points * self.tp_atr_mult * point
                tp1_price = entry_price + atr_points * 0.5 * point
                tp2_price = tp_price
                tp_source = "atr_fallback"
            
            print(f"{Utils.dateprint()} - SMART ETH: LONG SL/TP - SL_Source={sl_source}, TP_Source={tp_source}, "
                  f"Risk={risk_dist/point:.1f}pts, R:R={(tp_price-entry_price)/risk_dist:.1f}")
        
        else:
            sl_level = None
            sl_source = "none"
            
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
            
            if sl_level is None and liq_zones.get("nearest_short_liq"):
                sl_level = liq_zones["nearest_short_liq"]["price"]
                sl_source = "liquidation_cluster"
            
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
            
            risk_dist = sl_price - entry_price
            if risk_dist > 0:
                tp_target_price = None
                tp_source = "none"
                
                for liq in liq_zones.get("long_liquidation_zones", []):
                    if liq["price"] < entry_price:
                        tp_target_price = liq["price"]
                        tp_source = "long_liquidation_cluster"
                        break
                
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
            
            print(f"{Utils.dateprint()} - SMART ETH: SHORT SL/TP - SL_Source={sl_source}, TP_Source={tp_source}, "
                  f"Risk={risk_dist/point:.1f}pts, R:R={(entry_price-tp_price)/risk_dist:.1f}")
        
        return sl_price, tp_price, tp1_price, tp2_price

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "crypto") -> SignalEvent | None:
        symbol = data_event.symbol
        if not symbol_matches(symbol, self._allowed_symbols):
            return None

        trend_bars = self._load_bars(symbol, self.trend_timeframe, self.trend_slow_period + 30, data_provider)
        entry_bars = self._load_bars(symbol, self.entry_timeframe, max(self.ema_fast_period, self.ema_slow_period, self.rsi_period, self.fvg_lookback, self.fib_lookback) + 30, data_provider)
        if trend_bars.empty or entry_bars.empty or len(entry_bars) < max(self.ema_fast_period, self.ema_slow_period, self.rsi_period) + 3:
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
        if atr_points < getattr(self, 'min_atr_points', 100):
            return None

        # Get dynamic SR levels for asymmetric SL/TP with liquidation map
        sr_levels = self._get_dynamic_sr_levels(symbol, entry_bars, "BUY" if trend_is_bullish else "SELL")

        bull_fvg_ok = any(f["type"] == "bullish" and f["bottom"] < ask_price for f in fvgs) if self.use_fvg else True
        bear_fvg_ok = any(f["type"] == "bearish" and f["top"] > bid_price for f in fvgs) if self.use_fvg else True
        bull_fib_ok = self._is_price_at_fibonacci_support(ask_price, fib_levels) if self.use_fibonacci and fib_levels else True
        bear_fib_ok = self._is_price_at_fibonacci_resistance(bid_price, fib_levels) if self.use_fibonacci and fib_levels else True
        bull_macd_ok = current_macd > current_signal and current_macd > prev_macd if self.use_macd else True
        bear_macd_ok = current_macd < current_signal and current_macd < prev_macd if self.use_macd else True

        long_trigger = (
            trend_is_bullish
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
            sl_price, tp_price, tp1_price, tp2_price = self._calculate_asymmetric_sl_tp(
                ask_price, "BUY", sr_levels, atr_points, symbol_info, symbol
            )
            
            print(f"{Utils.dateprint()} - SMART ETH: LONG rsi={current_rsi:.2f} macd={current_macd:.5f} atr={atr_points:.2f} "
                  f"SL={sl_price:.2f} TP={tp_price:.2f} R:R={(tp_price-ask_price)/(ask_price-sl_price):.1f}")
            return SignalEvent(
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

        if short_trigger:
            sl_price, tp_price, tp1_price, tp2_price = self._calculate_asymmetric_sl_tp(
                bid_price, "SELL", sr_levels, atr_points, symbol_info, symbol
            )
            
            print(f"{Utils.dateprint()} - SMART ETH: SHORT rsi={current_rsi:.2f} macd={current_macd:.5f} atr={atr_points:.2f} "
                  f"SL={sl_price:.2f} TP={tp_price:.2f} R:R={(bid_price-tp_price)/(sl_price-bid_price):.1f}")
            return SignalEvent(
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

        return None
