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
from utils.symbol_utils import normalize_symbol, symbol_matches, get_asset_category
import config


class SignalEURUSDExtreme(ISignalGenerator):
    def __init__(self, properties: SmartMoneySignalProps, connector: PlatformConnector):
        self.entry_timeframe = "5min"
        self.trend_timeframe = "15min"
        self.connector = connector

        self.ema_fast = 9
        self.ema_slow = 21
        self.ema_trend_fast = 10
        self.ema_trend_slow = 20
        self.ema_filter = 50

        self.atr_period = max(getattr(properties, 'atr_period', 14), 2)
        extreme_params = getattr(config, "EXTREME_SCALPING_PARAMS", {}).get("EURUSD", {})
        self.sl_atr_mult = extreme_params.get("sl_atr_mult", 0.75)
        self.tp_atr_mult = extreme_params.get("tp_atr_mult", 2.2)
        self.min_atr_points = 12
        self.max_atr_points = 500

        self._allowed_symbols = ["EURUSD", "EURUSDc"]

    @staticmethod
    def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
        high_low = bars["high"] - bars["low"]
        high_close = (bars["high"] - bars["close"].shift(1)).abs()
        low_close = (bars["low"] - bars["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
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
    def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs()
        ], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, np.nan))
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        return dx.rolling(period).mean()

    def _in_session(self, bars: pd.DataFrame) -> bool:
        if bars.empty or len(bars) < 1:
            return False
        current_bar = bars.iloc[-1]
        if hasattr(current_bar, 'name') and hasattr(current_bar.name, 'hour'):
            hour = current_bar.name.hour
            return 7 <= hour < 21
        return True

    def _detect_order_block(self, bars: pd.DataFrame, signal_type: str) -> float | None:
        if len(bars) < 5:
            return None
        if signal_type == "BUY":
            for i in range(len(bars) - 3, max(len(bars) - 12, -1), -1):
                if bars["close"].iloc[i] < bars["open"].iloc[i]:
                    ob_low = bars["low"].iloc[i]
                    ob_high = bars["high"].iloc[i]
                    if bars["high"].iloc[-1] > bars["high"].iloc[i]:
                        return (ob_low + ob_high) / 2
        else:
            for i in range(len(bars) - 3, max(len(bars) - 12, -1), -1):
                if bars["close"].iloc[i] > bars["open"].iloc[i]:
                    ob_low = bars["low"].iloc[i]
                    ob_high = bars["high"].iloc[i]
                    if bars["low"].iloc[-1] < bars["low"].iloc[i]:
                        return (ob_low + ob_high) / 2
        return None

    def _detect_fvg(self, bars: pd.DataFrame, signal_type: str) -> float | None:
        if len(bars) < 3:
            return None
        c0 = bars.iloc[-1]
        c1 = bars.iloc[-2]
        c2 = bars.iloc[-3]

        if signal_type == "BUY":
            bullish_fvg = c0["low"] > c2["high"]
            if bullish_fvg:
                return (c2["high"] + c0["low"]) / 2
        else:
            bearish_fvg = c0["high"] < c2["low"]
            if bearish_fvg:
                return (c2["low"] + c0["high"]) / 2
        return None

    def _detect_liquidity_sweep(self, bars: pd.DataFrame, signal_type: str) -> bool:
        if len(bars) < 5:
            return False
        recent_low = bars["low"].iloc[-5:-1].min()
        recent_high = bars["high"].iloc[-5:-1].max()

        if signal_type == "BUY":
            return bars["low"].iloc[-1] < recent_low and bars["close"].iloc[-1] > bars["open"].iloc[-1]
        else:
            return bars["high"].iloc[-1] > recent_high and bars["close"].iloc[-1] < bars["open"].iloc[-1]

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol
        if not symbol_matches(symbol, self._allowed_symbols):
            return None

        trend_bars = data_provider.get_latest_closed_bars(symbol, self.trend_timeframe, 50)
        entry_bars = data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, 50)
        if trend_bars.empty or entry_bars.empty or len(entry_bars) < 30:
            return None

        if not self._in_session(entry_bars):
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

        spread_points = (ask_price - bid_price) / symbol_info.point
        min_spread_points = max(getattr(symbol_info, 'trade_stops_level', 0), 5)
        if spread_points > min_spread_points:
            return None

        atr_series = self._atr(entry_bars, self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        atr_points = current_atr / symbol_info.point
        if not np.isfinite(atr_points) or atr_points <= 0 or atr_points < self.min_atr_points:
            return None
        if atr_points > self.max_atr_points:
            return None

        trend_close = trend_bars["close"]
        trend_fast = self._ema(trend_close, self.ema_trend_fast)
        trend_slow = self._ema(trend_close, self.ema_trend_slow)
        trend_is_bullish = trend_close.iloc[-1] > trend_fast.iloc[-1] > trend_slow.iloc[-1]
        trend_is_bearish = trend_close.iloc[-1] < trend_fast.iloc[-1] < trend_slow.iloc[-1]

        if not trend_is_bullish and not trend_is_bearish:
            return None

        entry_close = entry_bars["close"]
        entry_high = entry_bars["high"]
        entry_low = entry_bars["low"]
        ema_fast = self._ema(entry_close, self.ema_fast)
        ema_slow = self._ema(entry_close, self.ema_slow)
        ema_filter = self._ema(entry_close, self.ema_filter)
        rsi_series = self._rsi(entry_close, 14)
        current_rsi = rsi_series.iloc[-1]
        adx_series = self._adx(entry_high, entry_low, entry_close, 14)
        current_adx = adx_series.iloc[-1] if not pd.isna(adx_series.iloc[-1]) else 0

        if current_adx < 18:
            return None

        ob_level = self._detect_order_block(entry_bars, "BUY" if trend_is_bullish else "SELL")
        fvg_level = self._detect_fvg(entry_bars, "BUY" if trend_is_bullish else "SELL")
        liquidity_sweep = self._detect_liquidity_sweep(entry_bars, "BUY" if trend_is_bullish else "SELL")

        min_stop_points = max(getattr(symbol_info, 'trade_stops_level', 0), 0) + 5
        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        long_trigger = (
            trend_is_bullish
            and ema_fast.iloc[-1] > ema_slow.iloc[-1]
            and ema_fast.iloc[-1] > ema_filter.iloc[-1]
            and entry_close.iloc[-1] > ema_fast.iloc[-1]
            and entry_close.iloc[-1] > entry_close.iloc[-2]
            and 40 <= current_rsi <= 65
            and (ob_level is None or ask_price > ob_level)
            and (fvg_level is None or ask_price > fvg_level)
        )

        short_trigger = (
            trend_is_bearish
            and ema_fast.iloc[-1] < ema_slow.iloc[-1]
            and ema_fast.iloc[-1] < ema_filter.iloc[-1]
            and entry_close.iloc[-1] < ema_fast.iloc[-1]
            and entry_close.iloc[-1] < entry_close.iloc[-2]
            and 35 <= current_rsi <= 60
            and (ob_level is None or bid_price < ob_level)
            and (fvg_level is None or bid_price < fvg_level)
        )

        if long_trigger:
            sl = ask_price - sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
            tp1 = ask_price + 0.618 * sl_distance_points * symbol_info.point
            tp2 = ask_price + 1.0 * sl_distance_points * symbol_info.point

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
                risk_pct_override=getattr(config, "EXTREME_SCALPING_PARAMS", {}).get(normalize_symbol(symbol), {}).get("risk_pct", 0.007),
            )

        if short_trigger:
            sl = bid_price + sl_distance_points * symbol_info.point
            tp = bid_price - tp_distance_points * symbol_info.point
            tp1 = bid_price - 0.618 * sl_distance_points * symbol_info.point
            tp2 = bid_price - 1.0 * sl_distance_points * symbol_info.point

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
                risk_pct_override=getattr(config, "EXTREME_SCALPING_PARAMS", {}).get(normalize_symbol(symbol), {}).get("risk_pct", 0.007),
            )

        return None
