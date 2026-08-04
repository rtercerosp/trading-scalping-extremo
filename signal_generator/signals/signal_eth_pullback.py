# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

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
from utils.symbol_utils import symbol_matches


class SignalETHPullback(ISignalGenerator):
    def __init__(self, properties: TrendPullbackProps, connector: PlatformConnector):
        self.entry_timeframe = "5min"
        self.connector = connector
        self.trend_timeframe = "15min"
        self.lookback = 30
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = 1.0
        self.tp_atr_mult = 1.5
        self.min_atr_points = 20
        self._allowed_symbols = ["ETHUSD", "ETHUSDc", "BTCUSD", "BTCUSDc"]

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

    def _get_asset_category(self, symbol: str) -> str:
        return "crypto"

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol
        if not symbol_matches(symbol, self._allowed_symbols):
            return None

        trend_bars = data_provider.get_latest_closed_bars(symbol, self.trend_timeframe, self.lookback + 10)
        entry_bars = data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, self.lookback + 10)
        if trend_bars.empty or entry_bars.empty or len(entry_bars) < self.lookback:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            print(f"{Utils.dateprint()} - SIGNAL ETH: Sin symbol_info para {symbol}")
            return None
        print(f"{Utils.dateprint()} - SIGNAL ETH: {symbol} point={symbol_info.point} trade_stops_level={symbol_info.trade_stops_level}")

        atr_series = self._atr(entry_bars, self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            print(f"{Utils.dateprint()} - SIGNAL ETH: ATR inválido {current_atr} para {symbol}")
            return None

        atr_points = current_atr / symbol_info.point
        if not np.isfinite(atr_points) or atr_points <= 0:
            print(f"{Utils.dateprint()} - SIGNAL ETH: ATR puntos inválido {atr_points} para {symbol}")
            return None
        if atr_points < self.min_atr_points:
            return None

        trend_close = trend_bars["close"]
        trend_fast = self._ema(trend_close, 10)
        trend_slow = self._ema(trend_close, 20)
        trend_is_bullish = trend_close.iloc[-1] > trend_fast.iloc[-1] > trend_slow.iloc[-1]
        trend_is_bearish = trend_close.iloc[-1] < trend_fast.iloc[-1] < trend_slow.iloc[-1]

        entry_close = entry_bars["close"]
        entry_ema = self._ema(entry_close, 9)
        rsi_series = self._rsi(entry_close, 14)
        current_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]

        current_close = entry_close.iloc[-1]
        prev_close = entry_close.iloc[-2]
        current_ema = entry_ema.iloc[-1]
        prev_ema = entry_ema.iloc[-2]

        long_pullback = prev_close <= prev_ema
        short_pullback = prev_close >= prev_ema

        long_trigger = (
            trend_is_bullish
            and current_close > current_ema
            and current_close > prev_close
            and current_rsi >= 52
            and current_rsi > prev_rsi
            and long_pullback
        )

        short_trigger = (
            trend_is_bearish
            and current_close < current_ema
            and current_close < prev_close
            and current_rsi <= 48
            and current_rsi < prev_rsi
            and short_pullback
        )

        min_stop_points = max(getattr(symbol_info, 'trade_stops_level', 0), 0) + 5
        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        ask_price = symbol_info.ask
        bid_price = symbol_info.bid
        if ask_price is None or bid_price is None:
            return None

        if trend_is_bullish and long_trigger and ask_price is not None:
            sl = ask_price - sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
            tp1 = ask_price + 0.8 * sl_distance_points * symbol_info.point
            tp2 = tp
            print(f"{Utils.dateprint()} - SIGNAL ETH: LONG sl_dist={sl_distance_points:.2f} sl={sl} tp={tp} ask={ask_price}")
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
            tp1 = bid_price - 0.8 * sl_distance_points * symbol_info.point
            tp2 = tp
            print(f"{Utils.dateprint()} - SIGNAL ETH: SHORT sl_dist={sl_distance_points:.2f} sl={sl} tp={tp} bid={bid_price}")
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
