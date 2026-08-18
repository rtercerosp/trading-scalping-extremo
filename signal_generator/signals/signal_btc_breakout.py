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


class SignalBTCBreakout(ISignalGenerator):
    def __init__(self, properties: TrendPullbackProps, connector: PlatformConnector):
        self.entry_timeframe = "5min"
        self.connector = connector
        self.lookback = 24
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = 0.8
        self.tp_atr_mult = 1.2
        self.min_atr_points = 80
        self._allowed_symbols = ["BTCUSD", "BTCUSDc"]

    @staticmethod
    def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
        high_low = bars["high"] - bars["low"]
        high_close = (bars["high"] - bars["close"].shift(1)).abs()
        low_close = (bars["low"] - bars["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    def _get_asset_category(self, symbol: str) -> str:
        return "crypto"

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                       portfolio: Portfolio, order_executor: OrderExecutor,
                       asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol
        if asset_category != "crypto":
            return None
        if not symbol_matches(symbol, self._allowed_symbols):
            return None

        bars = data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, self.lookback + 10)
        if bars.empty or len(bars) < self.lookback:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        atr_series = self._atr(bars, self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        atr_points = current_atr / symbol_info.point
        if atr_points < self.min_atr_points:
            return None

        recent_high = bars["high"].iloc[-self.lookback:-1].max()
        recent_low = bars["low"].iloc[-self.lookback:-1].min()
        current_close = bars["close"].iloc[-1]
        current_high = bars["high"].iloc[-1]
        current_low = bars["low"].iloc[-1]

        ask_price = last_tick.get("ask")
        bid_price = last_tick.get("bid")
        if ask_price is None or bid_price is None:
            return None

        min_stop_points = symbol_info.trade_stops_level + 5
        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        if current_high > recent_high and current_close > recent_high:
            sl = ask_price - sl_distance_points * symbol_info.point
            tp = ask_price + tp_distance_points * symbol_info.point
            tp1 = ask_price + 0.8 * sl_distance_points * symbol_info.point
            tp2 = tp

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

        if current_low < recent_low and current_close < recent_low:
            sl = bid_price + sl_distance_points * symbol_info.point
            tp = bid_price - tp_distance_points * symbol_info.point
            tp1 = bid_price - 0.8 * sl_distance_points * symbol_info.point
            tp2 = tp

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
