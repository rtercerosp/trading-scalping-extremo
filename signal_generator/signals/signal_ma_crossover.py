# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from platform_connector.platform_connector import PlatformConnector
from events.events import DataEvent, SignalEvent
from data_provider.data_provider import DataProvider
from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import MACrossoverProps
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor
import pandas as pd
from utils.symbol_utils import get_asset_category, normalize_symbol


class SignalMACrossover(ISignalGenerator):
    
    def __init__(self, properties: MACrossoverProps, connector: PlatformConnector):
        self.timeframe = properties.timeframe
        self.fast_period = properties.fast_period if properties.fast_period >= 20 else 50
        self.slow_period = properties.slow_period if properties.slow_period >= 100 else 200
        self.short_fast_period = max(properties.fast_period, 2) if properties.fast_period < 20 else 9
        self.short_slow_period = max(self.short_fast_period + 1, properties.slow_period) if properties.slow_period < 100 else 21
        self.connector = connector

        if self.fast_period >= self.slow_period:
            raise Exception(f"ERROR: el periodo rápido ({self.fast_period}) es mayor o igual al periodo lento ({self.slow_period}) para el cálculo de las medias móviles")

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.timeframe = entry_timeframe

    @staticmethod
    def _ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider, portfolio: Portfolio, order_executor: OrderExecutor, asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol

        bars = data_provider.get_latest_closed_bars(symbol, self.timeframe, self.slow_period + 10)
        if bars.empty or len(bars) < self.slow_period:
            return None

        close = bars["close"]
        long_fast = self._ema(close, self.fast_period)
        long_slow = self._ema(close, self.slow_period)
        short_fast = self._ema(close, self.short_fast_period)
        short_slow = self._ema(close, self.short_slow_period)

        signal = ""
        if long_fast.iloc[-1] > long_slow.iloc[-1] and short_fast.iloc[-1] > short_slow.iloc[-1]:
            signal = "BUY"
        elif long_fast.iloc[-1] < long_slow.iloc[-1] and short_fast.iloc[-1] < short_slow.iloc[-1]:
            signal = "SELL"

        if signal != "":
            last_tick = data_provider.get_latest_tick(symbol)
            if not last_tick:
                return None
            symbol_info = self.connector.get_symbol_info(symbol)
            if symbol_info is None:
                return None

            ask_price = last_tick.get("ask")
            bid_price = last_tick.get("bid")
            price = ask_price if signal == "BUY" else bid_price
            if price is None:
                return None

            if get_asset_category(normalize_symbol(symbol)) == "crypto":
                min_sl_points = max(5000, symbol_info.trade_stops_level + 50)
            elif get_asset_category(normalize_symbol(symbol)) == "gold":
                min_sl_points = max(300, symbol_info.trade_stops_level + 20)
            else:
                min_sl_points = max(50, symbol_info.trade_stops_level + 5)
            sl_distance_points = max(min_sl_points, symbol_info.trade_stops_level + 5)
            tp_distance_points = max(sl_distance_points * 2, symbol_info.trade_stops_level + 10)
            sl_distance = sl_distance_points * symbol_info.point
            tp_distance = tp_distance_points * symbol_info.point

            sl = price - sl_distance if signal == "BUY" else price + sl_distance
            tp = price + tp_distance if signal == "BUY" else price - tp_distance

            signal_event = SignalEvent(symbol=symbol,
                                    signal=signal,
                                    target_order="MARKET",
                                    target_price=0.0,
                                    magic_number=portfolio.magic,
                                    sl=sl,
                                    tp=tp)
            
            return signal_event
        return None
