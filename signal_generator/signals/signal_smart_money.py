# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import numpy as np
import pandas as pd

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from order_executor.order_executor import OrderExecutor
from portfolio.portfolio import Portfolio
from platform_connector.platform_connector import PlatformConnector

from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import SmartMoneySignalProps
from utils.utils import Utils
from utils.symbol_utils import get_asset_category


class SignalSmartMoney(ISignalGenerator):
    def __init__(self, properties: SmartMoneySignalProps, connector: PlatformConnector):
        self.entry_timeframe = properties.entry_timeframe
        self.trend_timeframe = properties.trend_timeframe
        self.trend_fast_period = max(properties.trend_fast_period, 2)
        self.trend_slow_period = max(properties.trend_slow_period, self.trend_fast_period + 1)
        self.ema_fast_period = max(properties.ema_fast_period, 2)
        self.ema_slow_period = max(properties.ema_slow_period, self.ema_fast_period + 1)
        self.rsi_period = max(properties.rsi_period, 2)
        self.rsi_bull_threshold = properties.rsi_bull_threshold
        self.rsi_bear_threshold = properties.rsi_bear_threshold
        self.macd_fast = max(properties.macd_fast, 2)
        self.macd_slow = max(properties.macd_slow, self.macd_fast + 1)
        self.macd_signal = max(properties.macd_signal, 1)
        self.fvg_lookback = max(properties.fvg_lookback, 2)
        self.fib_lookback = max(properties.fib_lookback, 10)
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = max(properties.sl_atr_mult, 0.5)
        self.tp_atr_mult = max(properties.tp_atr_mult, self.sl_atr_mult)
        self.min_liquidity_gap_points = properties.min_liquidity_gap_points
        self.use_fibonacci = properties.use_fibonacci
        self.use_fvg = properties.use_fvg
        self.use_macd = properties.use_macd
        self.connector = connector

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.entry_timeframe = entry_timeframe
        if trend_timeframe:
            self.trend_timeframe = trend_timeframe
        self._allowed_symbols: list[str] = []

    def _get_asset_category(self, symbol: str) -> str:
        return get_asset_category(symbol)

    def _get_spread_points(self, symbol_info, last_tick) -> float:
        ask = last_tick.get("ask") if last_tick else None
        bid = last_tick.get("bid") if last_tick else None
        if ask is None or bid is None or symbol_info is None or symbol_info.point <= 0:
            return 0.0
        return max((ask - bid) / symbol_info.point, 0.0)

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
    def _macd(series: pd.Series, fast: int, slow: int, signal: int) -> tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
        high_low = bars["high"] - bars["low"]
        high_close = (bars["high"] - bars["close"].shift(1)).abs()
        low_close = (bars["low"] - bars["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _detect_fvg(bars: pd.DataFrame, lookback: int) -> list[dict]:
        fvgs = []
        start = max(2, len(bars) - lookback)
        for i in range(start, len(bars)):
            prev_high = bars["high"].iloc[i - 2]
            curr_low = bars["low"].iloc[i]
            if curr_low > prev_high:
                fvgs.append({
                    "type": "bullish",
                    "top": prev_high,
                    "bottom": curr_low,
                    "index": i,
                    "midpoint": (prev_high + curr_low) / 2.0,
                })
            prev_low = bars["low"].iloc[i - 2]
            curr_high = bars["high"].iloc[i]
            if curr_high < prev_low:
                fvgs.append({
                    "type": "bearish",
                    "top": prev_low,
                    "bottom": curr_high,
                    "index": i,
                    "midpoint": (prev_low + curr_high) / 2.0,
                })
        return fvgs

    @staticmethod
    def _detect_liquidity_sweeps(bars: pd.DataFrame, lookback: int = 20) -> dict:
        if len(bars) < lookback + 1:
            return {"bullish_sweep": False, "bearish_sweep": False, "recent_high": 0.0, "recent_low": 0.0}
        recent_high = bars["high"].iloc[-lookback:-1].max()
        recent_low = bars["low"].iloc[-lookback:-1].min()
        bullish_sweep = bars["low"].iloc[-1] < recent_low and bars["close"].iloc[-1] > bars["open"].iloc[-1]
        bearish_sweep = bars["high"].iloc[-1] > recent_high and bars["close"].iloc[-1] < bars["open"].iloc[-1]
        return {
            "bullish_sweep": bullish_sweep,
            "bearish_sweep": bearish_sweep,
            "recent_high": recent_high,
            "recent_low": recent_low,
        }

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

    @staticmethod
    def _compute_fibonacci_levels(high: float, low: float) -> dict:
        diff = high - low
        return {
            "0.0": high,
            "0.236": high - 0.236 * diff,
            "0.382": high - 0.382 * diff,
            "0.5": high - 0.5 * diff,
            "0.618": high - 0.618 * diff,
            "0.786": high - 0.786 * diff,
            "1.0": low,
        }

    def _is_price_at_fibonacci_support(self, price: float, fib_levels: dict, tolerance: float = 0.001) -> bool:
        for level_name, level_price in fib_levels.items():
            if abs(price - level_price) / max(level_price, 1e-9) < tolerance:
                return True
        return False

    def _is_price_at_fibonacci_resistance(self, price: float, fib_levels: dict, tolerance: float = 0.001) -> bool:
        return self._is_price_at_fibonacci_support(price, fib_levels, tolerance=tolerance)

    def _compute_tp_levels(self, entry_price: float, sl: float, atr_points: float, asset_category: str, signal_type: str = "BUY") -> tuple:
        if asset_category == "crypto":
            tp1_mult = 1.2
            tp2_mult = 1.5
        elif asset_category == "gold":
            tp1_mult = 0.35
            tp2_mult = 0.9
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

    def _adjust_sl_tp_for_spread(self, entry_price: float, sl: float, tp: float, tp1: float, tp2: float, spread_points: float, point: float, signal_type: str = "BUY") -> tuple:
        spread_buffer_points = spread_points * 1.5 + 20
        if signal_type == "BUY":
            min_sl = entry_price - spread_buffer_points * point
            if sl < min_sl:
                sl = min_sl
            min_tp = entry_price + spread_buffer_points * point
            if tp < min_tp:
                tp = min_tp
            if tp1 < min_tp:
                tp1 = min_tp + abs(tp1 - sl) * 0.5 if tp1 > sl else min_tp
            if tp2 < min_tp:
                tp2 = min_tp + abs(tp2 - sl) * 1.0 if tp2 > sl else min_tp
        else:
            max_sl = entry_price + spread_buffer_points * point
            if sl > max_sl:
                sl = max_sl
            max_tp = entry_price - spread_buffer_points * point
            if tp > max_tp:
                tp = max_tp
            if tp1 > max_tp:
                tp1 = max_tp - abs(sl - tp1) * 0.5 if tp1 < sl else max_tp
            if tp2 > max_tp:
                tp2 = max_tp - abs(sl - tp2) * 1.0 if tp2 < sl else max_tp
        return sl, tp, tp1, tp2

    def _load_bars(self, symbol: str, timeframe: str, lookback: int, data_provider: DataProvider) -> pd.DataFrame:
        return data_provider.get_latest_closed_bars(symbol, timeframe, lookback)

    def generate_signal(
        self,
        data_event: DataEvent,
        data_provider: DataProvider,
        portfolio: Portfolio,
        order_executor: OrderExecutor,
        asset_category: str = "forex",
    ) -> SignalEvent | None:
        raise NotImplementedError("Use a concrete Smart Money strategy per asset.")
