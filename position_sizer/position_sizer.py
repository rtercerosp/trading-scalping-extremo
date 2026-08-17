# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from queue import Queue
from data_provider.data_provider import DataProvider
from platform_connector.platform_connector import PlatformConnector
from events.events import SignalEvent, SizingEvent
from .interfaces.position_sizer_interface import IPositionSizer
from .properties.position_sizer_properties import BaseSizingProps, RiskPctSizingProps
from .position_sizers.risk_pct_position_sizer import RiskPctPositionSizer

class PositionSizer(IPositionSizer):
    """
    Clase gestora que encapsula la lógica de dimensionamiento de posición.
    Actúa como una fábrica para seleccionar y utilizar el método de dimensionamiento
    específico basado en las propiedades de configuración.
    """
    def __init__(
        self,
        events_queue: Queue,
        data_provider: DataProvider,
        sizing_properties: BaseSizingProps,
        connector: PlatformConnector,
        get_risk_pct_callback=None,
        portfolio=None,
        max_leverage_factor=None,
    ):
        self.events_queue = events_queue
        self.data_provider = data_provider
        self.connector = connector
        self.sizing_method = self._get_sizing_method(sizing_properties, get_risk_pct_callback, portfolio, max_leverage_factor)

    def _get_sizing_method(self, sizing_props: BaseSizingProps, get_risk_pct_callback=None, portfolio=None, max_leverage_factor=None) -> IPositionSizer:
        if isinstance(sizing_props, RiskPctSizingProps):
            return RiskPctPositionSizer(properties=sizing_props, connector=self.connector, get_risk_pct_callback=get_risk_pct_callback, portfolio=portfolio, max_leverage_factor=max_leverage_factor)

        raise Exception(f"ERROR: Método de Position Sizing desconocido: {sizing_props}")

    def size_signal(self, signal_event: SignalEvent) -> None:
        """
        Calcula el volumen para una señal y, si es válido, crea y encola un SizingEvent.
        """
        volume = self.sizing_method.size_signal(signal_event, self.data_provider)

        if volume > 0.0:
            sizing_event = SizingEvent(
                symbol=signal_event.symbol,
                signal=signal_event.signal,
                target_order=signal_event.target_order,
                target_price=signal_event.target_price,
                magic_number=signal_event.magic_number,
                sl=signal_event.sl,
                tp=signal_event.tp,
                tp1=signal_event.tp1,
                tp2=signal_event.tp2,
                volume=volume,
                strategy_name=signal_event.strategy_name,
                primary_strategy_name=signal_event.primary_strategy_name,
                asset_category=signal_event.asset_category,
                market_regime=signal_event.market_regime,
                analysis_context=signal_event.analysis_context,
                risk_pct_override=signal_event.risk_pct_override,
                quality_score=signal_event.quality_score,
                justification=signal_event.justification,
            )
            self.events_queue.put(sizing_event)
