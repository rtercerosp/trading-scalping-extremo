# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from utils.utils import Utils
from platform_connector.platform_connector import PlatformConnector
from notifications.notifications import NotificationService
import pandas as pd
import logging
from typing import Dict, Optional, Callable
from datetime import datetime, timedelta
from events.events import DataEvent
from queue import Queue

logger = logging.getLogger(__name__)


class DataProvider():

    def __init__(self, events_queue: Queue, symbol_list: list, timeframe: str, connector: PlatformConnector, notification_service: NotificationService = None, stop_callback: Optional[Callable] = None):
        self.events_queue = events_queue
        self.symbols: list = symbol_list
        self.timeframe: str = timeframe
        self.connector = connector
        self.notification_service = notification_service
        self.stop_callback = stop_callback

        self.last_bar_datetime: Dict[str, datetime] = {symbol: datetime.min for symbol in self.symbols}
        self._bars_cache: Dict[str, tuple] = {}
        self._bars_cache_ttl = timedelta(seconds=30)

    def get_latest_closed_bar(self, symbol: str, timeframe: str) -> pd.Series:
        """Retrieves the latest closed bar for a given symbol and timeframe."""
        return self.connector.get_latest_closed_bar(symbol, timeframe)

    def get_latest_closed_bars(self, symbol: str, timeframe: str, num_bars: int = 1) -> pd.DataFrame:
        cache_key = f"{symbol}:{timeframe}"
        cached = self._bars_cache.get(cache_key)
        if cached is not None:
            data, ts = cached
            if datetime.now() - ts <= self._bars_cache_ttl and data is not None and not data.empty:
                return data.tail(num_bars)
        result = self.connector.get_latest_closed_bars(symbol, timeframe, num_bars)
        self._bars_cache[cache_key] = (result, datetime.now())
        return result

    def get_latest_tick(self, symbol: str) -> dict:
        """
        Retrieves the latest tick for the given symbol.

        Parameters:
        symbol (str): The symbol for which to retrieve the latest tick.

        Returns:
        dict: A dictionary containing the latest tick information.
        """
        tick = self.connector.get_symbol_info_tick(symbol)
        return tick._asdict() if tick is not None else {}

    def _notify_connection_loss(self, symbol: str) -> None:
        message = f"Error de conexión MT5: No se pudieron recuperar datos de {symbol}. Se detiene el trading."
        logger.error("DATA PROVIDER: %s", message)
        if self.notification_service:
            try:
                self.notification_service.send_notification(
                    title="🚨 ERROR DE CONEXIÓN MT5",
                    message=message
                )
            except Exception as e:
                logger.error("DATA PROVIDER: No se pudo enviar notificación: %s", e, exc_info=True)
        if self.stop_callback:
            try:
                self.stop_callback()
            except Exception as e:
                logger.error("DATA PROVIDER: Error en stop_callback: %s", e, exc_info=True)

    def check_for_new_data(self) -> None:
        """
        Checks for new data for each symbol and adds it to the events queue if available.

        This method iterates over the symbols and checks if there is new data available for each symbol.
        If new data is found, it updates the last retrieved bar for the symbol and adds a DataEvent to the events queue.

        Returns:
            None
        """
        max_consecutive_failures = 3
        consecutive_failures = 0

        for symbol in self.symbols:
            try:
                latest_bar = self.get_latest_closed_bar(symbol, self.timeframe)

                if latest_bar.empty or not hasattr(latest_bar, 'name') or latest_bar.name is None:
                    consecutive_failures += 1
                    if consecutive_failures >= max_consecutive_failures:
                        self._notify_connection_loss(symbol)
                        raise RuntimeError(f"No hay datos válidos para {symbol} después de {max_consecutive_failures} intentos")
                    logger.warning("DATA PROVIDER: Datos vacíos para %s", symbol)
                    continue

                if latest_bar.name > self.last_bar_datetime[symbol]:
                    self.last_bar_datetime[symbol] = latest_bar.name
                    data_event = DataEvent(symbol=symbol, data=latest_bar)
                    self.events_queue.put(data_event)
                    logger.info("DATA PROVIDER: Nueva vela para %s (%s)", symbol, latest_bar.name)

                consecutive_failures = 0
            except RuntimeError:
                raise
            except Exception as e:
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    self._notify_connection_loss(symbol)
                    raise RuntimeError(f"Error obteniendo datos de {symbol}: {str(e)}")
                logger.warning("DATA PROVIDER: Error obteniendo datos de %s: %s", symbol, str(e))
