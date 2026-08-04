from __future__ import annotations

import numpy as np
import pandas as pd

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from order_executor.order_executor import OrderExecutor
from portfolio.portfolio import Portfolio
from platform_connector.platform_connector import PlatformConnector

from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import TrendPullbackProps
from utils.utils import Utils
from utils.symbol_utils import normalize_symbol


class SignalTrendPullback(ISignalGenerator):
    def __init__(self, properties: TrendPullbackProps, connector: PlatformConnector):
        self.entry_timeframe = properties.entry_timeframe
        self.trend_timeframe = properties.trend_timeframe
        self.trend_fast_period = properties.trend_fast_period
        self.trend_slow_period = max(properties.trend_slow_period, properties.trend_fast_period + 1)
        self.setup_ema_period = properties.setup_ema_period
        self.rsi_period = max(properties.rsi_period, 2)
        self.rsi_bull_threshold = properties.rsi_bull_threshold
        self.rsi_bear_threshold = properties.rsi_bear_threshold
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = max(properties.sl_atr_mult, 0.5)
        self.tp_atr_mult = max(properties.tp_atr_mult, self.sl_atr_mult)
        self.connector = connector

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.entry_timeframe = entry_timeframe
        if trend_timeframe:
            self.trend_timeframe = trend_timeframe

    @staticmethod
    def _ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def _rsi(series: pd.Series, period: int) -> pd.Series:
        delta = series.diff()
        gains = delta.clip(lower=0.0)
        losses = -delta.clip(upper=0.0)
        avg_gain = gains.rolling(period).mean()
        avg_loss = losses.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.where(avg_loss != 0, 100.0)
        rsi = rsi.where(avg_gain != 0, 0.0)
        flat_mask = (avg_gain == 0) & (avg_loss == 0)
        return rsi.where(~flat_mask, 50.0)

    @staticmethod
    def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
        high_low = bars["high"] - bars["low"]
        high_close = (bars["high"] - bars["close"].shift(1)).abs()
        low_close = (bars["low"] - bars["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _detect_fvg(bars: pd.DataFrame) -> list:
        fvgs = []
        for i in range(2, len(bars)):
            prev_high = bars["high"].iloc[i - 2]
            curr_low = bars["low"].iloc[i]
            if curr_low > prev_high:
                fvg = {
                    "top": prev_high,
                    "bottom": curr_low,
                    "index": i,
                    "midpoint": (prev_high + curr_low) / 2.0,
                }
                fvgs.append(fvg)
        return fvgs

    @staticmethod
    def _detect_smart_money_bos(bars: pd.DataFrame, period: int = 5) -> dict:
        last_close = bars["close"].iloc[-1]
        last_high = bars["high"].iloc[-1]
        last_low = bars["low"].iloc[-1]

        recent_highs = bars["high"].iloc[-period:].max()
        recent_lows = bars["low"].iloc[-period:].min()

        bos_bullish = last_close > recent_highs
        bos_bearish = last_close < recent_lows

        return {
            "bos_bullish": bos_bullish,
            "bos_bearish": bos_bearish,
            "recent_high": recent_highs,
            "recent_low": recent_lows,
            "last_close": last_close,
        }

    @staticmethod
    def _detect_order_block(bars: pd.DataFrame) -> dict:
        last_bar = bars.iloc[-1]
        prev_bar = bars.iloc[-2]
        prev_prev_bar = bars.iloc[-3]

        bull_ob = prev_prev_bar["close"] > prev_prev_bar["open"] and prev_bar["low"] < prev_prev_bar["low"]
        bear_ob = prev_prev_bar["close"] < prev_prev_bar["open"] and prev_bar["high"] > prev_prev_bar["high"]

        return {
            "bull_order_block": bull_ob,
            "bear_order_block": bear_ob,
            "bull_ob_price": prev_prev_bar["low"] if bull_ob else 0.0,
            "bear_ob_price": prev_prev_bar["high"] if bear_ob else 0.0,
        }

    def _load_entry_bars(self, symbol: str, data_provider: DataProvider) -> pd.DataFrame:
        lookback = max(self.setup_ema_period + 10, self.rsi_period + 10, self.atr_period + 10, 40)
        return data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, lookback)

    def _load_trend_bars(self, symbol: str, data_provider: DataProvider) -> pd.DataFrame:
        lookback = max(self.trend_slow_period + 10, 40)
        return data_provider.get_latest_closed_bars(symbol, self.trend_timeframe, lookback)

    def _compute_tp_levels(self, entry_price: float, sl: float, atr_points: float, asset_category: str, signal_type: str = "BUY") -> tuple:
        if asset_category == "crypto":
            tp1_mult = 0.8
            tp2_mult = 1.5
        elif asset_category == "gold":
            tp1_mult = 1.0
            tp2_mult = 2.0
        else:
            tp1_mult = 0.3
            tp2_mult = 0.8

        sl_distance = abs(entry_price - sl)
        if signal_type == "SELL":
            tp1 = entry_price - tp1_mult * sl_distance if sl_distance > 0 else entry_price
            tp2 = entry_price - tp2_mult * sl_distance if sl_distance > 0 else entry_price
        else:
            tp1 = entry_price + tp1_mult * sl_distance if sl_distance > 0 else entry_price
            tp2 = entry_price + tp2_mult * sl_distance if sl_distance > 0 else entry_price

        return tp1, tp2

    def generate_signal(
        self,
        data_event: DataEvent,
        data_provider: DataProvider,
        portfolio: Portfolio,
        order_executor: OrderExecutor,
        asset_category: str = "forex",
    ) -> SignalEvent | None:
        symbol = data_event.symbol
        entry_bars = self._load_entry_bars(symbol, data_provider)
        trend_bars = self._load_trend_bars(symbol, data_provider)

        if entry_bars.empty or trend_bars.empty:
            return None
        if len(entry_bars) < max(self.setup_ema_period, self.rsi_period, self.atr_period) + 3:
            return None
        if len(trend_bars) < self.trend_slow_period + 1:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        entry_close = entry_bars["close"]
        trend_close = trend_bars["close"]

        entry_ema = self._ema(entry_close, self.setup_ema_period)
        trend_fast = self._ema(trend_close, self.trend_fast_period)
        trend_slow = self._ema(trend_close, self.trend_slow_period)
        rsi_series = self._rsi(entry_close, self.rsi_period)
        atr_series = self._atr(entry_bars, self.atr_period)

        current_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]
        current_atr = atr_series.iloc[-1]

        if pd.isna(current_rsi) or pd.isna(prev_rsi) or pd.isna(current_atr) or current_atr <= 0:
            return None

        current_close = entry_close.iloc[-1]
        prev_close = entry_close.iloc[-2]
        prev_high = entry_bars["high"].iloc[-2]
        prev_low = entry_bars["low"].iloc[-2]
        current_ema = entry_ema.iloc[-1]
        prev_ema = entry_ema.iloc[-2]

        trend_is_bullish = trend_close.iloc[-1] > trend_fast.iloc[-1] > trend_slow.iloc[-1]
        trend_is_bearish = trend_close.iloc[-1] < trend_fast.iloc[-1] < trend_slow.iloc[-1]

        long_pullback = prev_close <= prev_ema or entry_bars["low"].iloc[-2] <= prev_ema
        short_pullback = prev_close >= prev_ema or entry_bars["high"].iloc[-2] >= prev_ema

        long_trigger = (
            current_close > current_ema
            and current_close > prev_high
            and current_rsi >= self.rsi_bull_threshold
            and current_rsi > prev_rsi
        )
        short_trigger = (
            current_close < current_ema
            and current_close < prev_low
            and current_rsi <= self.rsi_bear_threshold
            and current_rsi < prev_rsi
        )

        fvgs = self._detect_fvg(entry_bars)
        smart_money = self._detect_smart_money_bos(entry_bars)
        order_block = self._detect_order_block(entry_bars)

        has_fvg_bullish = len(fvgs) > 0 and fvgs[-1]["bottom"] < current_close
        has_smart_money_bull = smart_money["bos_bullish"] or order_block["bull_order_block"]
        has_smart_money_bear = smart_money["bos_bearish"] or order_block["bear_order_block"]

        min_stop_points = symbol_info.trade_stops_level + 5
        atr_points = current_atr / symbol_info.point
        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        ask_price = last_tick.get("ask")
        bid_price = last_tick.get("bid")

        if trend_is_bullish and long_trigger and ask_price is not None:
            sl = ask_price - sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
            tp1, tp2 = self._compute_tp_levels(ask_price, sl, atr_points, asset_category, signal_type="BUY")

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

        if trend_is_bearish and short_trigger and bid_price is not None:
            sl = bid_price + sl_distance_points * symbol_info.point
            tp = bid_price - tp_distance_points * symbol_info.point
            tp1, tp2 = self._compute_tp_levels(bid_price, sl, atr_points, asset_category, signal_type="SELL")

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
