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


class SignalBTCStructureBreakout(ISignalGenerator):
    def __init__(self, properties: TrendPullbackProps, connector: PlatformConnector):
        self.entry_timeframe = "5min"
        self.connector = connector
        self.trend_timeframe = "15min"
        self.lookback = 30
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = 1.0
        self.tp_atr_mult = 1.5
        self.min_atr_points = 20
        self.breakout_lookback = 3
        self._allowed_symbols = ["BTCUSD", "BTCUSDc", "ETHUSD", "ETHUSDc"]

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.entry_timeframe = entry_timeframe
        if trend_timeframe:
            self.trend_timeframe = trend_timeframe

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
        if trend_bars.empty or entry_bars.empty or len(entry_bars) < self.breakout_lookback + 1:
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: datos insuficientes trend={trend_bars.empty} entry={entry_bars.empty} len={len(entry_bars)}")
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: sin symbol_info")
            return None

        trend_close = trend_bars["close"]
        trend_fast = self._ema(trend_close, 10)
        trend_slow = self._ema(trend_close, 20)
        fast_slope = trend_fast.iloc[-1] - trend_fast.iloc[-2]
        strict_bullish = trend_close.iloc[-1] > trend_fast.iloc[-1] > trend_slow.iloc[-1]
        strict_bearish = trend_close.iloc[-1] < trend_fast.iloc[-1] < trend_slow.iloc[-1]
        trend_is_bullish = strict_bullish or (trend_close.iloc[-1] > trend_fast.iloc[-1] and fast_slope > 0)
        trend_is_bearish = strict_bearish or (trend_close.iloc[-1] < trend_fast.iloc[-1] and fast_slope < 0)
        if not trend_is_bullish and not trend_is_bearish:
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: sin tendencia clara 15min bullish={trend_is_bullish} bearish={trend_is_bearish}")
            return None

        atr_series = self._atr(entry_bars, self.atr_period)
        current_atr = atr_series.iloc[-1]
        if pd.isna(current_atr) or current_atr <= 0:
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: ATR inválido")
            return None
        atr_points = current_atr / symbol_info.point
        if not np.isfinite(atr_points) or atr_points <= 0 or atr_points < self.min_atr_points:
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: ATR pts={atr_points:.2f} debajo de {self.min_atr_points}")
            return None

        entry_close = entry_bars["close"]
        entry_high = entry_bars["high"]
        entry_low = entry_bars["low"]
        entry_volume = entry_bars["volume"] if "volume" in entry_bars.columns else pd.Series([0] * len(entry_bars), index=entry_bars.index)
        rsi_series = self._rsi(entry_close, 14)
        current_rsi = rsi_series.iloc[-1]

        recent_high = entry_high.iloc[-self.breakout_lookback - 1:-1].max()
        recent_low = entry_low.iloc[-self.breakout_lookback - 1:-1].min()
        current_close = entry_close.iloc[-1]
        prev_close = entry_close.iloc[-2]

        avg_volume = entry_volume.iloc[-11:-1].mean() if len(entry_volume) >= 10 else entry_volume.iloc[:-1].mean()
        current_volume = entry_volume.iloc[-1]
        volume_ok = current_volume > avg_volume if avg_volume > 0 else True

        min_stop_points = max(getattr(symbol_info, 'trade_stops_level', 0), 0) + 5
        sl_distance_points = max(self.sl_atr_mult * atr_points, min_stop_points)
        tp_distance_points = max(self.tp_atr_mult * atr_points, min_stop_points)

        ask_price = symbol_info.ask
        bid_price = symbol_info.bid
        if ask_price is None or bid_price is None:
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: sin ask/bid")
            return None

        spread = ask_price - bid_price
        print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: {symbol} ask={ask_price} bid={bid_price} spread={spread:.2f} point={symbol_info.point}")

        long_trigger = (
            trend_is_bullish
            and current_close > recent_high
            and current_close > prev_close
            and volume_ok
            and 40 <= current_rsi <= 70
        )

        short_trigger = (
            trend_is_bearish
            and current_close < recent_low
            and current_close < prev_close
            and volume_ok
            and 30 <= current_rsi <= 60
        )

        if long_trigger and ask_price is not None:
            sl_structure = entry_low.iloc[-1] - sl_distance_points * symbol_info.point
            sl = min(sl_structure, ask_price - sl_distance_points * symbol_info.point)
            tp = ask_price + tp_distance_points * symbol_info.point
            tp1 = ask_price + 0.8 * sl_distance_points * symbol_info.point
            tp2 = tp
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: LONG sl_dist={sl_distance_points:.2f} sl={sl} tp={tp} ask={ask_price} rsi={current_rsi:.2f} vol_ok={volume_ok}")
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

        if short_trigger and bid_price is not None:
            sl_structure = entry_high.iloc[-1] + sl_distance_points * symbol_info.point
            sl = max(sl_structure, bid_price + sl_distance_points * symbol_info.point)
            tp = bid_price - tp_distance_points * symbol_info.point
            tp1 = bid_price - 0.8 * sl_distance_points * symbol_info.point
            tp2 = tp
            print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: SHORT sl_dist={sl_distance_points:.2f} sl={sl} tp={tp} bid={bid_price} rsi={current_rsi:.2f} vol_ok={volume_ok}")
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

        print(f"{Utils.dateprint()} - SIGNAL BTC STRUCT: sin trigger close={current_close} prev={prev_close} rhigh={recent_high} rlow={recent_low} rsi={current_rsi:.2f} vol_ok={volume_ok}")
        return None
