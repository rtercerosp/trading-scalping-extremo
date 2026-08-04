# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from events.events import DataEvent, SignalEvent
from platform_connector.platform_connector import PlatformConnector
from data_provider.data_provider import DataProvider
from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import RSIProps
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor
import pandas as pd
import numpy as np

class SignalRSI(ISignalGenerator):
    
    def __init__(self, properties: RSIProps, connector: PlatformConnector):
        """
        Initializes the RSI Mean Reversion object.

        Args:
            properties (RSIMeanRev): The properties object containing the parameters for the RSI mean reversion.

        Raises:
            Exception: If the fast period is greater than or equal to the slow period.

        """
        self.connector = connector
        self.timeframe = properties.timeframe
        self.rsi_period = properties.rsi_period if properties.rsi_period > 2 else 2

        if properties.rsi_upper > 100 or properties.rsi_upper < 0:
            self.rsi_upper = 70
        else:
            self.rsi_upper = properties.rsi_upper

        if properties.rsi_lower > 100 or properties.rsi_lower < 0:
            self.rsi_lower = 30
        else:
            self.rsi_lower = properties.rsi_lower
        
        if self.rsi_lower >= self.rsi_upper:
            raise Exception(f"ERROR: el nivel superior ({self.rsi_upper}) es menor o igual al nivel inferior ({self.rsi_lower}) para el cálculo de las señales de entrada")
        
        if properties.sl_points > 0:
            self.sl_points = properties.sl_points
        else:
            self.sl_points = 0

        if properties.tp_points > 0:
            self.tp_points = properties.tp_points
        else:
            self.tp_points = 0

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.timeframe = entry_timeframe if rsi_timeframe is None else rsi_timeframe


    def compute_rsi(self, prices: pd.Series) -> float:

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        average_gain = np.mean(gains[-self.rsi_period:])
        average_loss = np.mean(losses[-self.rsi_period:])

        if average_loss == 0 and average_gain == 0:
            return 50.0
        if average_loss == 0:
            return 100.0
        if average_gain == 0:
            return 0.0

        rs = average_gain / average_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    
    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider, portfolio: Portfolio, order_executor: OrderExecutor, asset_category: str = "forex") -> SignalEvent | None:
        symbol = data_event.symbol

        bars = data_provider.get_latest_closed_bars(symbol, self.timeframe, self.rsi_period + 1)
        if len(bars) < self.rsi_period + 1:
            return None

        rsi = self.compute_rsi(bars['close'])

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None
        
        symbol_info = self.connector.get_symbol_info(symbol)
        if not symbol_info:
            print(f"No se pudo obtener información del símbolo {symbol}")
            return None
        
        points = symbol_info.point
        stops_level = symbol_info.trade_stops_level
        min_sl_tp_distance_points = stops_level + 5

        if asset_category == "crypto":
            min_sl_points = max(300, min_sl_tp_distance_points)
            min_tp_points = max(600, min_sl_points * 2)
        elif asset_category == "gold":
            min_sl_points = max(150, min_sl_tp_distance_points)
            min_tp_points = max(300, min_sl_points * 2)
        else:
            min_sl_points = max(self.sl_points, min_sl_tp_distance_points) if self.sl_points > 0 else min_sl_tp_distance_points
            min_tp_points = max(self.tp_points, min_sl_points * 2) if self.tp_points > 0 else min_sl_points * 2

        signal = ""
        sl = 0.0
        tp = 0.0

        if rsi < self.rsi_lower:
            signal = "BUY"
            ask_price = last_tick.get('ask')
            if ask_price is None:
                return None
            sl = ask_price - min_sl_points * points
            tp = ask_price + min_tp_points * points

        elif rsi > self.rsi_upper:
            signal = "SELL"
            bid_price = last_tick.get('bid')
            if bid_price is None:
                return None
            sl = bid_price + min_sl_points * points
            tp = bid_price - min_tp_points * points

        if signal != "":
            signal_event = SignalEvent(symbol=symbol,
                                    signal=signal,
                                    target_order="MARKET",
                                    target_price=0.0,
                                    magic_number=portfolio.magic,
                                    sl=sl,
                                    tp=tp)
            
            return signal_event
        return None
