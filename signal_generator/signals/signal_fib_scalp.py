import numpy as np
import pandas as pd

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from order_executor.order_executor import OrderExecutor
from portfolio.portfolio import Portfolio
from platform_connector.platform_connector import PlatformConnector

from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import SmartMoneySignalProps
from ..signals.signal_smart_money import SignalSmartMoney
from utils.utils import Utils
from utils.symbol_utils import get_asset_category, normalize_symbol, symbol_matches


class SignalFibScalp(SignalSmartMoney):
    def __init__(self, properties: SmartMoneySignalProps, connector: PlatformConnector):
        super().__init__(properties, connector)
        self._allowed_symbols = ["EURUSD", "EURUSD.", "EURUSDc", "GBPUSD", "GBPUSD.", "GBPUSDc"]

    def _compute_fibonacci_extension(self, swing_high: float, swing_low: float, signal_type: str) -> dict:
        diff = swing_high - swing_low
        levels = {
            "0.0": swing_high,
            "0.618": swing_high - 0.618 * diff,
            "1.0": swing_low,
            "1.618": swing_low - 0.618 * diff,
            "2.0": swing_low - 1.0 * diff,
            "2.618": swing_low - 1.618 * diff,
        }
        if signal_type == "BUY":
            return {k: swing_low + (swing_high - float(v)) for k, v in levels.items()}
        return levels

    def _compute_fibonacci_retracement_entry(self, swing_high: float, swing_low: float, signal_type: str) -> float:
        diff = swing_high - swing_low
        if signal_type == "BUY":
            return swing_low + 0.618 * diff
        else:
            return swing_high - 0.618 * diff

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol
        if not symbol_matches(symbol, self._allowed_symbols):
            return None

        trend_bars = self._load_bars(symbol, self.trend_timeframe, 50, data_provider)
        entry_bars = self._load_bars(symbol, self.entry_timeframe, 100, data_provider)
        if trend_bars.empty or entry_bars.empty or len(entry_bars) < 30:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        ask_price = last_tick.get("ask")
        bid_price = last_tick.get("bid")
        if ask_price is None or bid_price is None:
            return None

        entry_close = entry_bars["close"]
        ema_fast = self._ema(entry_close, self.ema_fast_period)
        ema_slow = self._ema(entry_close, self.ema_slow_period)
        rsi_series = self._rsi(entry_close, self.rsi_period)
        atr_series = self._atr(entry_bars, self.atr_period)
        macd_line, signal_line, histogram = self._macd(entry_close, self.macd_fast, self.macd_slow, self.macd_signal)

        current_rsi = rsi_series.iloc[-1]
        current_atr = atr_series.iloc[-1]
        current_macd = macd_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        current_signal = signal_line.iloc[-1]

        if pd.isna(current_rsi) or pd.isna(current_atr) or current_atr <= 0:
            return None

        atr_points = current_atr / symbol_info.point
        spread_points = self._get_spread_points(symbol_info, last_tick)
        min_atr_points = getattr(symbol_info, 'trade_stops_level', 0) + 20
        if atr_points < min_atr_points:
            return None

        swing_high = entry_bars["high"].iloc[-20:-1].max()
        swing_low = entry_bars["low"].iloc[-20:-1].min()
        fib_levels = self._compute_fibonacci_levels(swing_high, swing_low)
        fib_extensions = self._compute_fibonacci_extension(swing_high, swing_low, "BUY")

        min_stop_points = symbol_info.trade_stops_level + 5
        if get_asset_category(normalize_symbol(symbol)) == "gold":
            min_stop_points = max(min_stop_points, 150)
        elif get_asset_category(normalize_symbol(symbol)) == "crypto":
            min_stop_points = max(min_stop_points, 100)

        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        bull_fib_ok = self._is_price_at_fibonacci_support(ask_price, fib_levels, tolerance=0.005)
        bear_fib_ok = self._is_price_at_fibonacci_resistance(bid_price, fib_levels, tolerance=0.005)

        macd_bull = current_macd > current_signal
        macd_bear = current_macd < current_signal

        price_above_ema = ask_price > ema_fast.iloc[-1]
        price_below_ema = bid_price < ema_fast.iloc[-1]

        long_trigger = (
            price_above_ema
            and 45 <= current_rsi <= 68
            and macd_bull
            and bull_fib_ok
        )

        short_trigger = (
            price_below_ema
            and 32 <= current_rsi <= 58
            and macd_bear
            and bear_fib_ok
        )

        if long_trigger:
            sl = ask_price - sl_distance_points * symbol_info.point
            tp1 = ask_price + 0.618 * sl_distance_points * symbol_info.point
            tp2 = ask_price + 1.618 * sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
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
            tp1 = bid_price - 0.618 * sl_distance_points * symbol_info.point
            tp2 = bid_price - 1.618 * sl_distance_points * symbol_info.point
            tp = bid_price - tp_distance_points * symbol_info.point
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
