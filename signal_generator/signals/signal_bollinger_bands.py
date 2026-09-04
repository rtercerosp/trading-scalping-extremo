# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import pandas as pd
import numpy as np
from typing import Optional, Literal

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
    squeeze_lookback: int = 20
    walk_basis_points: int = 50
    walk_min_candles: int = 3
    reversal_exit_std: float = 0.5
    atr_period: int = 14
    sl_atr_mult: float = 1.2
    tp_atr_mult: float = 2.0
    min_squeeze_duration: int = 5
    volatility_regime_threshold: float = 0.10


class SignalBollingerBands(ISignalGenerator):
    """
    Bollinger Bands Signal Generator with Three Volatility Regimes:
    
    1. SQUEEZE (Contracción Extrema): Bandwidth < threshold, precio rompe la banda media
       -> Entrada direccional en el breakout con SL en banda media, TP amplio
    
    2. WALK (Caminata en Banda Exterior): Precio camina sobre banda superior/inferior en tendencia fuerte
       -> Entrada en dirección de la tendencia con SL en banda media, TP extendido
    
    3. REVERSIÓN (Rechazo en Banda Extrema): Precio toca banda extrema y bandwidth se contrae
       -> Entrada contrarian hacia la banda media con SL ajustado
    """
    
    def __init__(self, properties: BollingerBandsProps, connector: PlatformConnector):
        self.entry_timeframe = properties.entry_timeframe
        self.connector = connector
        self.bb_period = max(properties.bb_period, 5)
        self.bb_std_dev = max(properties.bb_std_dev, 0.5)
        self.squeeze_threshold_pct = max(properties.squeeze_threshold_pct, 0.01)
        self.squeeze_lookback = max(properties.squeeze_lookback, 10)
        self.walk_basis_points = max(properties.walk_basis_points, 10)
        self.walk_min_candles = max(properties.walk_min_candles, 2)
        self.reversal_exit_std = max(properties.reversal_exit_std, 0.1)
        self.atr_period = max(properties.atr_period, 2)
        self.sl_atr_mult = max(properties.sl_atr_mult, 0.5)
        self.tp_atr_mult = max(properties.tp_atr_mult, self.sl_atr_mult)
        self.min_squeeze_duration = max(properties.min_squeeze_duration, 3)
        self.volatility_regime_threshold = max(properties.volatility_regime_threshold, 0.05)

    def set_timeframes(self, entry_timeframe: str, trend_timeframe: str | None = None, rsi_timeframe: str | None = None) -> None:
        self.entry_timeframe = entry_timeframe

    def _apply_asset_overrides(self, symbol: str) -> None:
        symbol_key = normalize_symbol(symbol)
        category = get_asset_category(symbol_key)
        if category == "crypto":
            self.bb_period = 21
            self.bb_std_dev = 2.2
            self.squeeze_threshold_pct = 0.06
            self.squeeze_lookback = 20
            self.walk_basis_points = 80
            self.walk_min_candles = 3
            self.reversal_exit_std = 0.6
            self.atr_period = 14
            self.sl_atr_mult = 1.1
            self.tp_atr_mult = 2.5
        elif category == "gold":
            self.bb_period = 20
            self.bb_std_dev = 2.0
            self.squeeze_threshold_pct = 0.04
            self.squeeze_lookback = 20
            self.walk_basis_points = 60
            self.walk_min_candles = 3
            self.reversal_exit_std = 0.5
            self.atr_period = 14
            self.sl_atr_mult = 1.0
            self.tp_atr_mult = 2.2
        elif category == "index":
            self.bb_period = 20
            self.bb_std_dev = 2.0
            self.squeeze_threshold_pct = 0.05
            self.squeeze_lookback = 20
            self.walk_basis_points = 50
            self.walk_min_candles = 3
            self.reversal_exit_std = 0.5
            self.atr_period = 14
            self.sl_atr_mult = 1.2
            self.tp_atr_mult = 2.0
        else:  # forex, commodity
            self.bb_period = 20
            self.bb_std_dev = 2.0
            self.squeeze_threshold_pct = 0.05
            self.squeeze_lookback = 20
            self.walk_basis_points = 50
            self.walk_min_candles = 3
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
    def _bollinger_bands(series: pd.Series, period: int, std_dev: float) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
        middle = series.rolling(period).mean()
        std = series.rolling(period).std(ddof=0)
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        bandwidth = (upper - lower) / middle.replace(0, float("nan"))
        return middle, upper, lower, bandwidth

    def _detect_volatility_regime(
        self, 
        bandwidth: pd.Series, 
        close: pd.Series,
        upper: pd.Series,
        lower: pd.Series,
        middle: pd.Series
    ) -> Literal["squeeze", "walk", "reversal", "neutral"]:
        """
        Detect the current volatility regime based on Bollinger Bands behavior.
        
        Returns:
            "squeeze" - Bandwidth contraction, potential breakout
            "walk" - Price walking along outer band in strong trend
            "reversal" - Price rejection at outer band with bandwidth contracting
            "neutral" - No clear regime
        """
        if len(bandwidth) < max(self.squeeze_lookback, self.walk_min_candles + 2):
            return "neutral"
        
        current_bandwidth = bandwidth.iloc[-1]
        prev_bandwidth = bandwidth.iloc[-2]
        
        # Calculate bandwidth percentile over lookback
        recent_bandwidth = bandwidth.iloc[-self.squeeze_lookback:]
        bw_percentile = (recent_bandwidth <= current_bandwidth).mean()
        
        # Current price position
        current_close = close.iloc[-1]
        current_upper = upper.iloc[-1]
        current_lower = lower.iloc[-1]
        current_middle = middle.iloc[-1]
        
        # === REGIME 1: SQUEEZE ===
        # Bandwidth at historical lows (bottom 20th percentile) AND below absolute threshold
        is_squeeze = (bw_percentile <= 0.20) and (current_bandwidth < self.squeeze_threshold_pct)
        
        # Additional squeeze confirmation: bandwidth has been contracting
        bw_contracting = current_bandwidth < prev_bandwidth
        
        if is_squeeze and bw_contracting:
            return "squeeze"
        
        # === REGIME 2: WALK ===
        # Price consistently outside outer band for multiple candles
        # Check upper band walk (bullish)
        upper_walk_count = 0
        for i in range(1, min(self.walk_min_candles + 1, len(close))):
            if close.iloc[-i] > upper.iloc[-i]:
                upper_walk_count += 1
            else:
                break
        
        # Check lower band walk (bearish)
        lower_walk_count = 0
        for i in range(1, min(self.walk_min_candles + 1, len(close))):
            if close.iloc[-i] < lower.iloc[-i]:
                lower_walk_count += 1
            else:
                break
        
        if upper_walk_count >= self.walk_min_candles:
            return "walk"
        if lower_walk_count >= self.walk_min_candles:
            return "walk"
        
        # === REGIME 3: REVERSAL ===
        # Price at/rejecting outer band WITH bandwidth contracting from expansion
        # Upper band rejection
        at_upper = abs(current_close - current_upper) / current_upper < 0.001 if current_upper > 0 else False
        bw_expanded_then_contracted = (prev_bandwidth > current_bandwidth) and (prev_bandwidth > self.volatility_regime_threshold)
        
        if at_upper and bw_expanded_then_contracted:
            return "reversal"
        
        # Lower band rejection
        at_lower = abs(current_close - current_lower) / current_lower < 0.001 if current_lower > 0 else False
        if at_lower and bw_expanded_then_contracted:
            return "reversal"
        
        return "neutral"

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider,
                        portfolio: Portfolio, order_executor: OrderExecutor,
                        asset_category: str = "forex") -> Optional[SignalEvent]:
        symbol = data_event.symbol
        self._apply_asset_overrides(symbol)
        lookback = self.bb_period + self.squeeze_lookback + 10
        bars = data_provider.get_latest_closed_bars(symbol, self.entry_timeframe, lookback)
        if bars.empty or len(bars) < self.bb_period + self.squeeze_lookback:
            return None

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            return None

        symbol_info = self.connector.get_symbol_info(symbol)
        if symbol_info is None:
            return None

        close = bars["close"]
        middle, upper, lower, bandwidth = self._bollinger_bands(close, self.bb_period, self.bb_std_dev)
        
        if pd.isna(middle.iloc[-1]) or pd.isna(upper.iloc[-1]) or pd.isna(lower.iloc[-1]):
            return None

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

        # Detect volatility regime
        regime = self._detect_volatility_regime(bandwidth, close, upper, lower, middle)
        
        signal = None
        entry_price = None
        sl = None
        tp = None
        regime_detail = ""

        if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]) and pd.notna(middle.iloc[-1]):
            
            if regime == "squeeze":
                # SQUEEZE REGIME: Bandwidth contracted, wait for breakout
                # Breakout above upper band -> BUY
                if ask > upper.iloc[-1] and ask > middle.iloc[-1]:
                    signal = "BUY"
                    entry_price = ask
                    sl = middle.iloc[-1]  # SL at middle band
                    tp = entry_price + tp_distance * 1.5  # Extended TP for breakout
                    regime_detail = "SQUEEZE_BREAKOUT_LONG"
                
                # Breakout below lower band -> SELL
                elif bid < lower.iloc[-1] and bid < middle.iloc[-1]:
                    signal = "SELL"
                    entry_price = bid
                    sl = middle.iloc[-1]  # SL at middle band
                    tp = entry_price - tp_distance * 1.5  # Extended TP for breakout
                    regime_detail = "SQUEEZE_BREAKOUT_SHORT"
            
            elif regime == "walk":
                # WALK REGIME: Price walking along outer band
                # Upper band walk -> BUY (trend following)
                if ask > upper.iloc[-1] and ask > middle.iloc[-1]:
                    # Confirm walk: price has been above upper for multiple candles
                    walk_confirmed = True
                    for i in range(1, min(self.walk_min_candles + 1, len(close))):
                        if close.iloc[-i] <= upper.iloc[-i]:
                            walk_confirmed = False
                            break
                    
                    if walk_confirmed:
                        signal = "BUY"
                        entry_price = ask
                        sl = middle.iloc[-1]  # SL at middle band
                        tp = entry_price + tp_distance * 2.0  # Very extended TP for trend
                        regime_detail = "WALK_UPPER_BAND"
                
                # Lower band walk -> SELL (trend following)
                elif bid < lower.iloc[-1] and bid < middle.iloc[-1]:
                    walk_confirmed = True
                    for i in range(1, min(self.walk_min_candles + 1, len(close))):
                        if close.iloc[-i] >= lower.iloc[-i]:
                            walk_confirmed = False
                            break
                    
                    if walk_confirmed:
                        signal = "SELL"
                        entry_price = bid
                        sl = middle.iloc[-1]  # SL at middle band
                        tp = entry_price - tp_distance * 2.0  # Very extended TP for trend
                        regime_detail = "WALK_LOWER_BAND"
            
            elif regime == "reversal":
                # REVERSAL REGIME: Rejection at outer band with bandwidth contracting
                # Rejection at upper band -> SELL (mean reversion)
                if prev_bandwidth > current_bandwidth and abs(ask - upper.iloc[-1]) < self.reversal_exit_std * current_atr * point:
                    signal = "SELL"
                    entry_price = bid
                    sl = upper.iloc[-1] + min_sl_distance  # SL just above upper band
                    tp = middle.iloc[-1]  # Target middle band (mean reversion)
                    regime_detail = "REVERSAL_UPPER_BAND"
                
                # Rejection at lower band -> BUY (mean reversion)
                elif prev_bandwidth > current_bandwidth and abs(bid - lower.iloc[-1]) < self.reversal_exit_std * current_atr * point:
                    signal = "BUY"
                    entry_price = ask
                    sl = lower.iloc[-1] - min_sl_distance  # SL just below lower band
                    tp = middle.iloc[-1]  # Target middle band (mean reversion)
                    regime_detail = "REVERSAL_LOWER_BAND"
            
            # Fallback: Traditional breakout logic if no clear regime
            if signal is None:
                # Price breaks above upper with bandwidth expanding
                if ask > upper.iloc[-1] and ask > middle.iloc[-1] and (ask - upper.iloc[-1]) >= self.walk_basis_points * point:
                    signal = "BUY"
                    entry_price = ask
                    sl = middle.iloc[-1]
                    tp = entry_price + tp_distance
                    regime_detail = "BREAKOUT_UPPER"
                
                # Price breaks below lower with bandwidth expanding
                elif bid < lower.iloc[-1] and bid < middle.iloc[-1] and (lower.iloc[-1] - bid) >= self.walk_basis_points * point:
                    signal = "SELL"
                    entry_price = bid
                    sl = middle.iloc[-1]
                    tp = entry_price - tp_distance
                    regime_detail = "BREAKOUT_LOWER"
        else:
            return None

        if sl is None or tp is None or sl <= 0 or tp <= 0:
            return None

        # Quality scoring based on regime
        quality_scores = {
            "SQUEEZE_BREAKOUT_LONG": 75.0,
            "SQUEEZE_BREAKOUT_SHORT": 75.0,
            "WALK_UPPER_BAND": 80.0,
            "WALK_LOWER_BAND": 80.0,
            "REVERSAL_UPPER_BAND": 70.0,
            "REVERSAL_LOWER_BAND": 70.0,
            "BREAKOUT_UPPER": 65.0,
            "BREAKOUT_LOWER": 65.0,
        }
        
        quality_score = quality_scores.get(regime_detail, 60.0)
        
        justification = (
            f"Bollinger Bands [{regime_detail}]: "
            f"bandwidth={current_bandwidth:.4f} (pctile={(bandwidth.iloc[-self.squeeze_lookback:] <= current_bandwidth).mean():.0%}), "
            f"precio={'sobre banda superior' if signal == 'BUY' else 'bajo banda inferior'}, "
            f"ATR={current_atr:.4f}, "
            f"régimen={regime}"
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