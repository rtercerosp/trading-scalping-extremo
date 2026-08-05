from platform_connector.platform_connector import PlatformConnector
from events.events import DataEvent, SignalEvent
from data_provider.data_provider import DataProvider
from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import TrendPullbackProps
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor
from utils.utils import Utils
import pandas as pd
import numpy as np


class SignalCandlestickPatterns(ISignalGenerator):
    def __init__(self, properties: TrendPullbackProps, connector: PlatformConnector):
        self.entry_timeframe = properties.entry_timeframe
        self.connector = connector
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = max(properties.sl_atr_mult, 0.5)
        self.tp_atr_mult = max(properties.tp_atr_mult, self.sl_atr_mult)
        self.rsi_period = max(properties.rsi_period, 2)

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.entry_timeframe = entry_timeframe

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

    def _detect_hammer(self, row: pd.Series, prev: pd.Series, is_bullish: bool) -> bool:
        body = abs(row["close"] - row["open"])
        upper_wick = row["high"] - max(row["open"], row["close"])
        lower_wick = min(row["open"], row["close"]) - row["low"]
        total_range = row["high"] - row["low"]
        if total_range <= 0 or body <= 0:
            return False
        if body > total_range * 0.4:
            return False
        if is_bullish:
            return lower_wick >= body * 2 and upper_wick <= body * 0.5
        else:
            return upper_wick >= body * 2 and lower_wick <= body * 0.5

    def _detect_engulfing(self, curr: pd.Series, prev: pd.Series, is_bullish: bool) -> bool:
        curr_body = abs(curr["close"] - curr["open"])
        prev_body = abs(prev["close"] - prev["open"])
        if curr_body <= prev_body:
            return False
        if is_bullish:
            return curr["open"] < prev["close"] and curr["close"] > prev["open"]
        else:
            return curr["open"] > prev["close"] and curr["close"] < prev["open"]

    def _detect_doji(self, row: pd.Series) -> bool:
        body = abs(row["close"] - row["open"])
        total_range = row["high"] - row["low"]
        if total_range <= 0:
            return False
        return body <= total_range * 0.1

    def _detect_pin_bar(self, row: pd.Series, is_bullish: bool) -> bool:
        body = abs(row["close"] - row["open"])
        upper_wick = row["high"] - max(row["open"], row["close"])
        lower_wick = min(row["open"], row["close"]) - row["low"]
        total_range = row["high"] - row["low"]
        if total_range <= 0 or body <= 0:
            return False
        if is_bullish:
            return lower_wick >= total_range * 0.6 and upper_wick <= body * 1.5
        else:
            return upper_wick >= total_range * 0.6 and lower_wick <= body * 1.5

    def _detect_three_soldiers_crows(self, bars: pd.DataFrame, is_bullish: bool) -> bool:
        if len(bars) < 4:
            return False
        c0, c1, c2, c3 = bars.iloc[-4], bars.iloc[-3], bars.iloc[-2], bars.iloc[-1]
        if is_bullish:
            return (
                c0["close"] < c0["open"]
                and c1["close"] > c1["open"] and c1["close"] > c0["open"]
                and c2["close"] > c2["open"] and c2["close"] > c1["close"]
                and c3["close"] > c3["open"] and c3["close"] > c2["close"]
            )
        else:
            return (
                c0["close"] > c0["open"]
                and c1["close"] < c1["open"] and c1["close"] < c0["open"]
                and c2["close"] < c2["open"] and c2["close"] < c1["close"]
                and c3["close"] < c3["open"] and c3["close"] < c2["close"]
            )

    def _get_asset_category(self, symbol: str) -> str:
        from utils.symbol_utils import get_asset_category
        return get_asset_category(symbol)

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol
        lookback = 210
        bars = data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, lookback + 10)
        if bars.empty or len(bars) < lookback:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        close = bars["close"]
        ema9 = self._ema(close, 9)
        ema21 = self._ema(close, 21)
        ema50 = self._ema(close, 50)
        ema200 = self._ema(close, 200)
        rsi_series = self._rsi(close, self.rsi_period)
        atr_series = self._atr(bars, self.atr_period)

        curr = bars.iloc[-1]
        prev = bars.iloc[-2]
        prev2 = bars.iloc[-3]

        current_ema9 = ema9.iloc[-1]
        current_ema21 = ema21.iloc[-1]
        current_ema50 = ema50.iloc[-1]
        current_ema200 = ema200.iloc[-1]
        current_rsi = rsi_series.iloc[-1]
        current_atr = atr_series.iloc[-1]

        if pd.isna(current_ema9) or pd.isna(current_ema21) or pd.isna(current_ema50) or pd.isna(current_ema200) or pd.isna(current_rsi) or pd.isna(current_atr) or current_atr <= 0:
            return None

        trend_is_bullish = curr["close"] > current_ema50 > current_ema200
        trend_is_bearish = curr["close"] < current_ema50 < current_ema200
        if not trend_is_bullish and not trend_is_bearish:
            return None

        ask_price = last_tick.get("ask")
        bid_price = last_tick.get("bid")
        if ask_price is None or bid_price is None:
            return None

        min_stop_points = symbol_info.trade_stops_level + 5
        atr_points = current_atr / symbol_info.point
        min_atr_points = getattr(symbol_info, 'trade_stops_level', 0) + 20
        if atr_points < min_atr_points:
            return None
        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        bullish_patterns = []
        bearish_patterns = []

        if self._detect_hammer(curr, prev, is_bullish=True):
            bullish_patterns.append("HAMMER")
        if self._detect_hammer(curr, prev, is_bullish=False):
            bearish_patterns.append("HANGING_MAN")
        if self._detect_pin_bar(curr, is_bullish=True):
            bullish_patterns.append("PIN_BAR_BULL")
        if self._detect_pin_bar(curr, is_bullish=False):
            bearish_patterns.append("PIN_BAR_BEAR")
        if self._detect_engulfing(curr, prev, is_bullish=True):
            bullish_patterns.append("BULL_ENGULFING")
        if self._detect_engulfing(curr, prev, is_bullish=False):
            bearish_patterns.append("BEAR_ENGULFING")
        if self._detect_doji(curr) and trend_is_bullish and current_rsi > 45:
            bullish_patterns.append("DOJI_BULL")
        if self._detect_doji(curr) and trend_is_bearish and current_rsi < 55:
            bearish_patterns.append("DOJI_BEAR")
        if self._detect_three_soldiers_crows(bars, is_bullish=True):
            bullish_patterns.append("THREE_SOLDIERS")
        if self._detect_three_soldiers_crows(bars, is_bullish=False):
            bearish_patterns.append("THREE_CROWS")

        short_term_bull = current_ema9 > current_ema21 and curr["close"] > current_ema9
        short_term_bear = current_ema9 < current_ema21 and curr["close"] < current_ema9

        long_trigger = (
            trend_is_bullish
            and short_term_bull
            and bullish_patterns
            and 48 <= current_rsi <= 68
        )

        short_trigger = (
            trend_is_bearish
            and short_term_bear
            and bearish_patterns
            and 32 <= current_rsi <= 52
        )

        if long_trigger:
            sl = ask_price - sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
            print(f"{Utils.dateprint()} - CANDLESTICK: LONG patterns={bullish_patterns} rsi={current_rsi:.2f} ema9={current_ema9:.5f} ema21={current_ema21:.5f}")
            return SignalEvent(
                symbol=symbol,
                signal="BUY",
                target_order="MARKET",
                target_price=0.0,
                magic_number=portfolio.magic,
                sl=sl,
                tp=tp,
            )

        if short_trigger:
            sl = bid_price + sl_distance_points * symbol_info.point
            tp = bid_price - tp_distance_points * symbol_info.point
            print(f"{Utils.dateprint()} - CANDLESTICK: SHORT patterns={bearish_patterns} rsi={current_rsi:.2f} ema9={current_ema9:.5f} ema21={current_ema21:.5f}")
            return SignalEvent(
                symbol=symbol,
                signal="SELL",
                target_order="MARKET",
                target_price=0.0,
                magic_number=portfolio.magic,
                sl=sl,
                tp=tp,
            )

        return None
