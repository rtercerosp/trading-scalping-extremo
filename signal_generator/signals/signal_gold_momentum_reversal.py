# signal_generator/signals/signal_gold_momentum_reversal.py

import logging
import pandas as pd
import pandas_ta as ta
from typing import Optional

from signal_generator.signals.base_signal import BaseSignal
from data_provider.data_provider import DataProvider
from events.events import DataEvent, SignalEvent
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor
from utils.symbol_utils import get_asset_category

logger = logging.getLogger(__name__)

class SignalGoldMomentumReversal(BaseSignal):
    """
    Genera señales de reversión para el oro (XAUUSD) basadas en agotamiento de momentum.
    Busca precios sobre-extendidos con RSI en extremos y patrones de velas de reversión.
    """
    def __init__(self, name: str, version: int, params: dict):
        super().__init__(name, version, params)
        self._strategy_name: str = "SignalGoldMomentumReversal"
        self._version: int = 1
        self._asset_category: str = "gold"  # Solo para oro

        # Parámetros de la estrategia
        self.ema_slow_period: int = self.params.get("ema_slow_period", 50)
        self.rsi_period: int = self.params.get("rsi_period", 14)
        self.rsi_overbought: float = self.params.get("rsi_overbought", 75.0)
        self.rsi_oversold: float = self.params.get("rsi_oversold", 25.0)
        self.atr_period: int = self.params.get("atr_period", 14)
        self.risk_reward_ratio: float = self.params.get("risk_reward_ratio", 2.0)

    def _get_asset_category(self, symbol: str) -> str:
        return get_asset_category(symbol)

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider, portfolio: Portfolio, order_executor: OrderExecutor, asset_category: str = "forex") -> Optional[SignalEvent]:
        symbol = data_event.symbol
        if self._get_asset_category(symbol) != self._asset_category:
            return None

        data = data_provider.get_latest_closed_bars(symbol, "15min", self.ema_slow_period + 10)
        if data.empty or len(data) <= self.ema_slow_period:
            return None

        try:
                # 1. Calcular indicadores
                data.ta.ema(length=self.ema_slow_period, append=True)
                data.ta.rsi(length=self.rsi_period, append=True)
                data.ta.atr(length=self.atr_period, append=True)

                ema_col = f'EMA_{self.ema_slow_period}'
                rsi_col = f'RSI_{self.rsi_period}'
                atr_col = f'ATRr_{self.atr_period}'

                if not all(c in data.columns for c in [ema_col, rsi_col, atr_col]):
                    logger.warning(f"[{self._strategy_name}] Faltan columnas de indicadores para {symbol}.")
                    return None

                # 2. Obtener datos recientes
                latest = data.iloc[-1]
                previous = data.iloc[-2]

                # 3. Detección de patrones de reversión
                # Patrón envolvente bajista
                is_bearish_engulfing = (previous['close'] > previous['open'] and
                                        latest['close'] < latest['open'] and
                                        latest['open'] > previous['close'] and
                                        latest['close'] < previous['open'])
                # Patrón envolvente alcista
                is_bullish_engulfing = (previous['close'] < previous['open'] and
                                        latest['close'] > latest['open'] and
                                        latest['open'] < previous['close'] and
                                        latest['close'] > previous['open'])

                signal_type = None
                quality_score = 0.0

                # 4. Lógica de señal
                if latest[rsi_col] > self.rsi_overbought and is_bearish_engulfing:
                    signal_type = "SELL"
                    sl = latest['high'] + latest[atr_col] * 0.2
                    tp = latest['close'] - (sl - latest['close']) * self.risk_reward_ratio
                    justification = f"Reversión bajista con RSI({latest[rsi_col]:.1f}) > {self.rsi_overbought} y patrón envolvente."
                    quality_score = 70 + (latest[rsi_col] - self.rsi_overbought)

                elif latest[rsi_col] < self.rsi_oversold and is_bullish_engulfing:
                    signal_type = "BUY"
                    sl = latest['low'] - latest[atr_col] * 0.2
                    tp = latest['close'] + (latest['close'] - sl) * self.risk_reward_ratio
                    justification = f"Reversión alcista con RSI({latest[rsi_col]:.1f}) < {self.rsi_oversold} y patrón envolvente."
                    quality_score = 70 + (self.rsi_oversold - latest[rsi_col])

                if signal_type:
                    return SignalEvent(
                        symbol=symbol, signal_type=signal_type, price=latest['close'], sl=sl, tp=tp,
                        strategy=self._strategy_name, version=self._version,
                        quality_score=min(max(quality_score, 0), 100), justification=justification
                    )

        except Exception as e:
            logger.error(f"[{self._strategy_name}] Error al generar señal para {symbol}: {e}", exc_info=True)

        return None