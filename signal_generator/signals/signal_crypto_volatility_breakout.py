# signal_generator/signals/signal_crypto_volatility_breakout.py

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

class SignalCryptoVolatilityBreakout(BaseSignal):
    """
    Genera señales para criptomonedas basadas en breakouts de volatilidad.
    Busca períodos de baja volatilidad (squeeze) seguidos de una ruptura
    con alto volumen, ideal para activos como BTC y ETH.
    """
    def __init__(self, name: str, version: int, params: dict):
        super().__init__(name, version, params)
        self._strategy_name: str = "SignalCryptoVolatilityBreakout"
        self._version: int = 1
        self._asset_category: str = "crypto" # Solo para criptomonedas
        self._allowed_symbols: Optional[list[str]] = None

        # Parámetros de la estrategia
        self.bb_length: int = self.params.get("bb_length", 20)
        self.bb_std: float = self.params.get("bb_std", 2.0)
        self.atr_period: int = self.params.get("atr_period", 14)
        self.volume_ma_period: int = self.params.get("volume_ma_period", 20)
        self.volume_factor: float = self.params.get("volume_factor", 1.8)
        self.squeeze_threshold_factor: float = self.params.get("squeeze_threshold_factor", 0.8)
        self.risk_reward_ratio: float = self.params.get("risk_reward_ratio", 2.5)

    def _get_asset_category(self, symbol: str) -> str:
        return get_asset_category(symbol)

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider, portfolio: Portfolio, order_executor: OrderExecutor, asset_category: str = "forex") -> Optional[SignalEvent]:
        symbol = data_event.symbol
        if self._get_asset_category(symbol) != self._asset_category:
            return None

        data = data_provider.get_latest_closed_bars(symbol, "15min", max(self.bb_length, self.volume_ma_period) + 10)
        if data.empty or len(data) <= max(self.bb_length, self.volume_ma_period):
            return None

        try:
                # 1. Calcular indicadores
                data.ta.bbands(length=self.bb_length, std=self.bb_std, append=True)
                data.ta.atr(length=self.atr_period, append=True)
                data['volume_ma'] = data['tickvol'].rolling(window=self.volume_ma_period).mean()
                
                # Renombrar columnas para consistencia
                bb_upper_col = f'BBU_{self.bb_length}_{self.bb_std}'
                bb_lower_col = f'BBL_{self.bb_length}_{self.bb_std}'
                bb_width_col = f'BBB_{self.bb_length}_{self.bb_std}'
                atr_col = f'ATRr_{self.atr_period}'

                if not all(c in data.columns for c in [bb_upper_col, bb_lower_col, bb_width_col, atr_col]):
                    logger.warning(f"[{self._strategy_name}] Faltan columnas de indicadores para {symbol}. Columnas disponibles: {data.columns.tolist()}")
                    return None

                # 2. Obtener los datos más recientes
                latest = data.iloc[-1]
                previous = data.iloc[-2]

                # 3. Detección de Squeeze (baja volatilidad)
                avg_bb_width = data[bb_width_col].rolling(window=self.bb_length).mean().iloc[-1]
                is_squeeze = latest[bb_width_col] < (avg_bb_width * self.squeeze_threshold_factor)

                # 4. Detección de Breakout y Volumen
                is_high_volume = latest['tickvol'] > (latest['volume_ma'] * self.volume_factor)
                buy_breakout = previous['close'] < previous[bb_upper_col] and latest['close'] > latest[bb_upper_col]
                sell_breakout = previous['close'] > previous[bb_lower_col] and latest['close'] < latest[bb_lower_col]

                signal_type = None
                sl = 0.0
                tp = 0.0

                if is_squeeze and is_high_volume:
                    if buy_breakout:
                        signal_type = "BUY"
                        sl = latest['low'] - latest[atr_col] * 0.5
                        tp = latest['close'] + (latest['close'] - sl) * self.risk_reward_ratio
                        justification = f"Breakout alcista desde squeeze con alto volumen (x{self.volume_factor:.1f})."
                        quality_score = 65 + (latest['tickvol'] / latest['volume_ma'] - self.volume_factor) * 10
                    
                    elif sell_breakout:
                        signal_type = "SELL"
                        sl = latest['high'] + latest[atr_col] * 0.5
                        tp = latest['close'] - (sl - latest['close']) * self.risk_reward_ratio
                        justification = f"Breakout bajista desde squeeze con alto volumen (x{self.volume_factor:.1f})."
                        quality_score = 65 + (latest['tickvol'] / latest['volume_ma'] - self.volume_factor) * 10

                if signal_type:
                    return SignalEvent(
                        symbol=symbol, signal_type=signal_type, price=latest['close'], sl=sl, tp=tp,
                        strategy=self._strategy_name, version=self._version,
                        quality_score=min(max(quality_score, 0), 100), justification=justification
                    )

        except Exception as e:
            logger.error(f"[{self._strategy_name}] Error al generar señal para {symbol}: {e}", exc_info=True)
        
        return None