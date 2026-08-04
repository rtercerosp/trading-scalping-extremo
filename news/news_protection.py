# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from queue import Queue
from platform_connector.platform_connector import PlatformConnector
from events.events import BaseEvent, DataEvent
from utils.utils import Utils
from utils.symbol_utils import get_asset_category, normalize_symbol
from datetime import datetime, timedelta
from pydantic import BaseModel
import time


class NewsEvent(BaseModel):
    symbol: str
    event_time: datetime
    impact: str
    description: str
    affects: list[str] = ["ALL"]

    class Config:
        arbitrary_types_allowed = True


class NewsProtection:
    def __init__(self, events_queue: Queue, connector: PlatformConnector):
        self.events_queue = events_queue
        self.connector = connector

        self.news_schedule: list[NewsEvent] = []
        self.news_window_minutes = 5
        self.enabled = True

        self._economic_calendar = None
        try:
            from news.economic_calendar import MT5EconomicCalendar
            self._economic_calendar = MT5EconomicCalendar(connector=connector, lookahead_hours=48, min_impact="MEDIUM")
        except Exception as e:
            logger.debug("NEWS: No se pudo inicializar MT5EconomicCalendar: %s", e, exc_info=True)

        self._load_news_schedule()

    def _load_news_schedule(self) -> None:
        now = datetime.now()
        horizon = now + timedelta(hours=48)

        self.news_schedule = [
            NewsEvent(symbol="USD", event_time=now.replace(hour=14, minute=30, second=0, microsecond=0), impact="HIGH", description="US CPI", affects=["ALL"]),
            NewsEvent(symbol="USD", event_time=now.replace(hour=20, minute=0, second=0, microsecond=0), impact="HIGH", description="US Fed Rate Decision", affects=["ALL"]),
            NewsEvent(symbol="USD", event_time=now.replace(hour=12, minute=30, second=0, microsecond=0), impact="HIGH", description="US NFP", affects=["ALL"]),
            NewsEvent(symbol="EUR", event_time=now.replace(hour=10, minute=0, second=0, microsecond=0), impact="HIGH", description="ECB Rate Decision", affects=["ALL"]),
            NewsEvent(symbol="EUR", event_time=now.replace(hour=9, minute=0, second=0, microsecond=0), impact="MEDIUM", description="EU GDP", affects=["ALL"]),
            NewsEvent(symbol="GBP", event_time=now.replace(hour=10, minute=30, second=0, microsecond=0), impact="HIGH", description="UK CPI", affects=["ALL"]),
            NewsEvent(symbol="JPY", event_time=now.replace(hour=12, minute=30, second=0, microsecond=0), impact="HIGH", description="Japan GDP", affects=["ALL"]),
            NewsEvent(symbol="XAU", event_time=now.replace(hour=14, minute=0, second=0, microsecond=0), impact="HIGH", description="US CPI (Gold impact)", affects=["XAUUSD"]),
            NewsEvent(symbol="XAU", event_time=now.replace(hour=20, minute=0, second=0, microsecond=0), impact="HIGH", description="US Fed Rate Decision (Gold impact)", affects=["XAUUSD"]),
            NewsEvent(symbol="BTC", event_time=now.replace(hour=16, minute=0, second=0, microsecond=0), impact="MEDIUM", description="US Fed Rate Decision (Crypto impact)", affects=["BTCUSD", "ETHUSD", "SOLUSD"]),
            NewsEvent(symbol="USD", event_time=now.replace(hour=15, minute=30, second=0, microsecond=0), impact="MEDIUM", description="US Retail Sales", affects=["ALL"]),
            NewsEvent(symbol="USD", event_time=now.replace(hour=11, minute=0, second=0, microsecond=0), impact="MEDIUM", description="US PPI", affects=["ALL"]),
        ]

        for i, event in enumerate(self.news_schedule):
            event_time = event.event_time
            while event_time < now:
                event_time += timedelta(days=1)
            self.news_schedule[i] = NewsEvent(
                symbol=event.symbol,
                event_time=event_time,
                impact=event.impact,
                description=event.description,
                affects=event.affects,
            )

        self.news_schedule = [
            e for e in self.news_schedule
            if now <= e.event_time <= horizon
        ]

    def _is_news_window_active(self, symbol: str) -> tuple:
        if not self.enabled:
            return False, None

        symbol_key = normalize_symbol(symbol)
        asset_category = get_asset_category(symbol_key)
        now = datetime.now()
        window_start = now - timedelta(minutes=self.news_window_minutes)
        window_end = now + timedelta(minutes=self.news_window_minutes)

        for news_event in self.news_schedule:
            if window_start <= news_event.event_time <= window_end:
                if "ALL" in news_event.affects or symbol_key in [a.upper() for a in news_event.affects]:
                    return True, news_event

        return False, None

    def check_symbol_for_news(self, symbol: str) -> tuple:
        in_window, news_event = self._is_news_window_active(symbol)
        if in_window and news_event:
            return True, f"Noticia: {news_event.description} (Impacto: {news_event.impact})"
        return False, ""

    def get_news_info_for_symbol(self, symbol: str) -> dict:
        symbol_key = normalize_symbol(symbol)
        asset_category = get_asset_category(symbol_key)
        now = datetime.now()
        window_start = now - timedelta(minutes=self.news_window_minutes)
        window_end = now + timedelta(minutes=self.news_window_minutes)

        active_events = []
        upcoming_events = []
        for news_event in self.news_schedule:
            if "ALL" in news_event.affects or symbol_key in [a.upper() for a in news_event.affects]:
                if window_start <= news_event.event_time <= window_end:
                    active_events.append({
                        "description": news_event.description,
                        "impact": news_event.impact,
                        "event_time": news_event.event_time.isoformat(),
                        "symbol": news_event.symbol,
                    })
                elif news_event.event_time > window_end:
                    upcoming_events.append({
                        "description": news_event.description,
                        "impact": news_event.impact,
                        "event_time": news_event.event_time.isoformat(),
                        "symbol": news_event.symbol,
                    })

        if self._economic_calendar:
            try:
                mt5_info = self._economic_calendar.get_events_for_symbol(symbol, window_minutes=self.news_window_minutes)
                for event in mt5_info.get("active", []):
                    event["source"] = "mt5"
                    active_events.append(event)
                for event in mt5_info.get("upcoming", []):
                    event["source"] = "mt5"
                    upcoming_events.append(event)
            except Exception as e:
                logger.debug("NEWS: Error obteniendo eventos MT5 para %s: %s", symbol, e, exc_info=True)

        return {
            "active": active_events,
            "upcoming": upcoming_events,
            "in_window": len(active_events) > 0,
            "asset_category": asset_category,
        }

    def check_and_close_positions_for_news(self, order_executor, portfolio) -> None:
        if not self.enabled:
            return

        now = datetime.now()
        window_start = now - timedelta(minutes=self.news_window_minutes)
        window_end = now + timedelta(minutes=self.news_window_minutes)

        for news_event in self.news_schedule:
            if window_start <= news_event.event_time <= window_end:
                positions = portfolio.get_strategy_open_positions()
                for position in positions:
                    symbol_key = normalize_symbol(position.symbol)
                    if "ALL" in news_event.affects or symbol_key in [a.upper() for a in news_event.affects]:
                        order_executor.close_position_by_ticket(position.ticket)
                        print(f"{Utils.dateprint()} - NEWS PROTECTION: Cerrando posición {position.ticket} en {position.symbol} por noticia: {news_event.description}")

    def get_upcoming_news(self, hours: int = 24) -> list:
        now = datetime.now()
        cutoff = now + timedelta(hours=hours)
        return [
            {
                "description": e.description,
                "impact": e.impact,
                "event_time": e.event_time.isoformat(),
                "symbol": e.symbol,
                "affects": e.affects,
            }
            for e in self.news_schedule if now <= e.event_time <= cutoff
        ]

    def add_custom_news_event(self, symbol: str, event_time: datetime, impact: str, description: str, affects: list = None) -> None:
        self.news_schedule.append(NewsEvent(
            symbol=symbol,
            event_time=event_time,
            impact=impact,
            description=description,
            affects=affects or ["ALL"],
        ))

    def process_data_event(self, data_event: DataEvent) -> None:
        in_window, news_info = self.check_symbol_for_news(data_event.symbol)
        if in_window:
            print(f"{Utils.dateprint()} - NEWS PROTECTION: Ventana de noticias activa para {data_event.symbol}: {news_info}")