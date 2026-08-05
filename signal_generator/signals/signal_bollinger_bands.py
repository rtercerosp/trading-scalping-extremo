# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import pandas as pd
from typing import Optional

from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor
from platform_connector.platform_connector import PlatformConnector

from ..interfaces.signal_generator_interface import ISignalGenerator
from ..properties.signal_generator_properties import BaseSignalProps
from utils.utils import Utils
from utils.symbol_utils import get_asset_category, normalize_symbol


class BollingerBandsProps(BaseSignalProps):
    entry_timeframe: str
    bb_period: int = 20
    bb_std_dev: float = 2.0
    squeeze_threshold_pct: float = 0.05
    walk_basis_points: int = 50
    reversal_exit_std: float = 0.5
    atr_period: int = 14
    sl_atr_mult: float = 1.2
    tp_atr_mult: float = 2.0


class SignalBollingerBands(ISignalGenerator):
    def __init__(self, properties: BollingerBandsProps, connector: PlatformConnector):
        self.entry_timeframe = properties.entry_timeframe
        self.connector = connector
        self.bb_period = max(properties.bb_period, 5)
        self.bb_std_dev = max(properties.bb_std_dev, 0.5)
        self.squeeze_threshold_pct = max(properties.squeeze_threshold_pct, 0.01)
        self.walk_basis_points = max(properties.walk_basis_points, 10)
        self.reversal_exit_std = max(properties.reversal_exit_std, 0.1)
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = max(properties.sl_atr_mult, 0.5)
        self.tp_atr_mult = max(properties.tp_atr_mult, self.sl_atr_mult)

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.entry_timeframe = entry_timeframe

    def _apply_asset_overrides(self, symbol: str) -> None:
        symbol_key = normalize_symbol(symbol)
        category = get_asset_category(symbol_key)
        if category == "crypto":
            self.bb_period = 21
            self.bb_std_dev = 2.2
            self.squeeze_threshold_pct = 0.06
            self.walk_basis_points = 80
            self.reversal_exit_std = 0.6
            self.atr_period = 14
            self.sl_atr_mult = 1.1
            self.tp_atr_mult = 2.5
        elif category == "gold":
            self.bb_period = 20
            self.bb_std_dev = 2.0
            self.squeeze_threshold_pct = 0.04
            self.walk_basis_points = 60
            self.reversal_exit_std = 0.5
            self.atr_period = 14
            self.sl_atr_mult = 1.0
            self.tp_atr_mult = 2.2
        else:
            self.bb_period = 20
            self.bb_std_dev = 2.0
            self.squeeze_threshold_pct = 0.05
            self.walk_basis_points = 50
            self.reversal_exit_std = 0.5
            self.atr_period = 14
            self.sl_atr_mult = 1.2
            self.tp_atr_mult = 2.0

    @staticmethod
    def _atr(bars: pd.DataFrame, period: int) -> pd.Series:
        high_low = bars["high"] - bars["low"]
        high_close = (bars["high"] - bars["close"].shift(1)).abs()
        low_close = (bars["low"] - bars["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()

    @staticmethod
    def _bollinger_bands(series: pd.Series, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series]:
        middle = series.rolling(period).mean()
        std = series.rolling(period).std(ddof=0)
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        bandwidth = (upper - lower) / middle.replace(0, float("nan"))
        return middle, upper, lower, bandwidth

    def _get_asset_category(self, symbol: str) -> str:
        from utils.symbol_utils import get_asset_category
        return get_asset_category(symbol)

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "forex") -> Optional[SignalEvent]:
        symbol = data_event.symbol
        self._apply_asset_overrides(symbol)
        lookback = self.bb_period + 20
        bars = data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, lookback)
        if bars.empty or len(bars) < self.bb_period + 1:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        close = bars["close"]
        middle, upper, lower, bandwidth = self._bollinger_bands(close, self.bb_period, self.bb_std_dev)
        current_bandwidth = bandwidth.iloc[-1]
        prev_bandwidth = bandwidth.iloc[-2] if len(bandwidth) > 1 else current_bandwidth

        atr_series = self._atr(bars, self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            return None

        ask = last_tick.get("ask")
        bid = last_tick.get("bid")
        if ask is None or bid is None:
            return None

        point = getattr(symbol_info, "point", 0.0001) or 0.0001
        min_stop_points = symbol_info.trade_stops_level + 5
        min_sl_distance = max(min_stop_points * point, current_atr * self.sl_atr_mult * point)
        tp_distance = max(min_sl_distance * 2, current_atr * self.tp_atr_mult * point)

        if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]) and pd.notna(middle.iloc[-1]):
            if current_bandwidth < self.squeeze_threshold_pct:
                sl = middle.iloc[-1] if ask > middle.iloc[-1] else middle.iloc[-1]
                if ask > middle.iloc[-1] and ask > upper.iloc[-1]:
                    signal = "BUY"
                    entry_price = ask
                    sl = min(entry_price - min_sl_distance, middle.iloc[-1])
                    tp = entry_price + tp_distance
                elif bid < middle.iloc[-1] and bid < lower.iloc[-1]:
                    signal = "SELL"
                    entry_price = bid
                    sl = max(entry_price + min_sl_distance, middle.iloc[-1])
                    tp = entry_price - tp_distance
                else:
                    return None
            elif ask > upper.iloc[-1] and ask > middle.iloc[-1] and (ask - upper.iloc[-1]) >= self.walk_basis_points * point:
                signal = "BUY"
                entry_price = ask
                sl = middle.iloc[-1]
                tp = entry_price + tp_distance
            elif bid < lower.iloc[-1] and bid < middle.iloc[-1] and (lower.iloc[-1] - bid) >= self.walk_basis_points * point:
                signal = "SELL"
                entry_price = bid
                sl = middle.iloc[-1]
                tp = entry_price - tp_distance
            elif prev_bandwidth > current_bandwidth and abs(ask - upper.iloc[-1]) < self.reversal_exit_std * current_atr * point:
                signal = "SELL"
                entry_price = bid
                sl = middle.iloc[-1]
                tp = entry_price - tp_distance
            elif prev_bandwidth > current_bandwidth and abs(bid - lower.iloc[-1]) < self.reversal_exit_std * current_atr * point:
                signal = "BUY"
                entry_price = ask
                sl = middle.iloc[-1]
                tp = entry_price + tp_distance
            else:
                return None
        else:
            return None

        if sl is None or tp is None or sl <= 0 or tp <= 0:
            return None

        quality_score = 70.0
        justification = (
            f"Bandas de Bollinger: bandwidth={current_bandwidth:.4f}, "
            f"precio={'sobre banda superior' if signal == 'BUY' else 'bajo banda inferior'}, "
            f"ATR={current_atr:.4f}"
        )

        signal_event = SignalEvent(
            symbol=symbol,
            signal=signal,
            target_order="MARKET",
            target_price=0.0,
            magic_number=portfolio.magic,
            sl=sl,
            tp=tp,
            quality_score=quality_score,
            justification=justification,
        )

        return signal_event
