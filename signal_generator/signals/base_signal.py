from typing import Optional
from events.events import DataEvent, SignalEvent
from data_provider.data_provider import DataProvider
from portfolio.portfolio import Portfolio
from order_executor.order_executor import OrderExecutor

class BaseSignal:
    def __init__(self, name: str, version: int, params: dict):
        self.name = name
        self.version = version
        self.params = params

    def generate_signal(self, data_event: DataEvent, data_provider: DataProvider, portfolio: Portfolio, order_executor: OrderExecutor, asset_category: str = "forex") -> Optional[SignalEvent]:
        raise NotImplementedError
