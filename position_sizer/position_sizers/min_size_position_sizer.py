# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from utils.utils import Utils
from platform_connector.platform_connector import PlatformConnector
from data_provider.data_provider import DataProvider
from events.events import SignalEvent
from ..interfaces.position_sizer_interface import IPositionSizer

class MinSizePositionSizer(IPositionSizer):

    def __init__(self, connector: PlatformConnector):
        self.connector = connector

    def size_signal(self, signal_event: SignalEvent, data_provider: DataProvider) -> float:
        
        volume = self.connector.get_symbol_info(signal_event.symbol).volume_min

        if volume is not None:
            return volume
        else:
            print(f"{Utils.dateprint()} - ERROR (MinSizePositionSizer): No se ha podido determinar el volumen mínimo para {signal_event.symbol}")
            return 0.0