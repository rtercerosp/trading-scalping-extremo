# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import numpy as np
import pandas as pd

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from order_executor.order_executor import OrderExecutor
from portfolio.portfolio import Portfolio
from platform_connector.platform_connector import PlatformConnector

from .signal_smart_money import SignalSmartMoney
from ..properties.signal_generator_properties import SmartMoneySignalProps
from utils.utils import Utils
from utils.symbol_utils import symbol_matches


class SignalSmartMoneyBTC(SignalSmartMoney):
    def __init__(self, properties: SmartMoneySignalProps, connector: PlatformConnector):
        super().__init__(properties, connector)
        self._allowed_symbols = ["BTCUSD", "BTCUSDc"]
        self.min_atr_points = 200

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        super().set_timeframes(entry_timeframe, trend_timeframe, rsi_timeframe)
        self._allowed_symbols = ["BTCUSD", "BTCUSDc"]

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
        if atr_points < getattr(self, 'min_atr_points', 200):
            return None

        spread_points = self._get_spread_points(symbol_info, last_tick)
        spread_buffer_points = spread_points * 1.5 + 20
        sl_distance_points = max(self.sl_atr_mult * atr_points + spread_buffer_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points + spread_buffer_points * 1.2, min_stop_points)

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
            sl = ask_price - sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
            tp1, tp2 = self._compute_tp_levels(ask_price, sl, atr_points, asset_category, signal_type="BUY")
            sl, tp, tp1, tp2 = self._adjust_sl_tp_for_spread(ask_price, sl, tp, tp1, tp2, spread_points, symbol_info.point, signal_type="BUY")
            print(f"{Utils.dateprint()} - SMART BTC: LONG rsi={current_rsi:.2f} macd={current_macd:.5f} atr={atr_points:.2f} spread={spread_points:.1f} pts")
            return SignalEvent(
                symbol=symbol,
                signal="BUY",
                target_order="MARKET",
                target_price=0.0,
                magic_number=portfolio.magic,
                sl=sl,
                tp=tp,
                tp1=tp1,
                tp2=tp2,
            )

        if short_trigger:
            sl = bid_price + sl_distance_points * symbol_info.point
            tp = bid_price - tp_distance_points * symbol_info.point
            tp1, tp2 = self._compute_tp_levels(bid_price, sl, atr_points, asset_category, signal_type="SELL")
            sl, tp, tp1, tp2 = self._adjust_sl_tp_for_spread(bid_price, sl, tp, tp1, tp2, spread_points, symbol_info.point, signal_type="SELL")
            print(f"{Utils.dateprint()} - SMART BTC: SHORT rsi={current_rsi:.2f} macd={current_macd:.5f} atr={atr_points:.2f} spread={spread_points:.1f} pts")
            return SignalEvent(
                symbol=symbol,
                signal="SELL",
                target_order="MARKET",
                target_price=0.0,
                magic_number=portfolio.magic,
                sl=sl,
                tp=tp,
                tp1=tp1,
                tp2=tp2,
            )

        return None
