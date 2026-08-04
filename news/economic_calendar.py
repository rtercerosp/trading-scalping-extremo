# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from datetime import datetime, timedelta
from typing import Optional
import logging
import json
import os

from news.news_protection import NewsEvent, NewsProtection

logger = logging.getLogger(__name__)


class MT5EconomicCalendar:
    def __init__(self, connector, lookahead_hours: int = 48, min_impact: str = "MEDIUM"):
        self.connector = connector
        self.lookahead_hours = max(lookahead_hours, 1)
        self.min_impact = min_impact
        self._events: list[dict] = []
        self._last_refresh: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=30)

    def _impact_rank(self, impact: str) -> int:
        impact = (impact or "").upper()
        if impact == "HIGH":
            return 3
        if impact == "MEDIUM":
            return 2
        if impact == "LOW":
            return 1
        return 0

    def _parse_mt5_event(self, raw: dict) -> Optional[dict]:
        try:
            event_time = raw.get("time") or raw.get("datetime") or raw.get("date")
            if event_time is None:
                return None
            if isinstance(event_time, datetime):
                dt = event_time
            else:
                dt = datetime.fromisoformat(str(event_time))
            impact = str(raw.get("impact", raw.get("importance", "LOW"))).upper()
            if self._impact_rank(impact) < self._impact_rank(self.min_impact):
                return None
            return {
                "event_time": dt,
                "impact": impact,
                "description": raw.get("name", raw.get("description", "Evento macro")),
                "symbol": raw.get("currency", raw.get("symbol", "USD")),
                "affects": raw.get("affects", ["ALL"]),
            }
        except Exception as e:
            logger.debug("ECON_CAL: Error parseando evento MT5: %s | raw=%s", e, raw)
            return None

    def _load_from_mt5(self) -> list[dict]:
        try:
            if self.connector is None:
                return []
            mt5 = self.connector.mt5 if hasattr(self.connector, "mt5") else None
            if mt5 is None or not hasattr(mt5, "calendar_events"):
                return self._load_fallback()
            from_date = datetime.utcnow()
            to_date = from_date + timedelta(hours=self.lookahead_hours)
            raw_events = mt5.calendar_events(from_date=from_date, to_date=to_date)
            if not raw_events:
                return []
            events = []
            for raw in raw_events:
                parsed = self._parse_mt5_event(raw)
                if parsed:
                    events.append(parsed)
            return events
        except Exception as e:
            logger.error("ECON_CAL: Error cargando eventos desde MT5: %s", e, exc_info=True)
            return []

    def _load_fallback(self) -> list[dict]:
        try:
            fallback_path = "news/economic_calendar_fallback.json"
            if os.path.exists(fallback_path):
                with open(fallback_path, "r", encoding="utf-8") as f:
                    raw_events = json.load(f)
                events = []
                for raw in raw_events:
                    parsed = self._parse_mt5_event(raw)
                    if parsed:
                        events.append(parsed)
                return events
        except Exception as e:
            logger.error("ECON_CAL: Error cargando fallback de calendario económico: %s", e, exc_info=True)
        return []

    def refresh(self, force: bool = False) -> list[dict]:
        now = datetime.now()
        if not force and self._last_refresh and (now - self._last_refresh) < self._cache_ttl:
            return self._events
        self._events = self._load_from_mt5()
        self._last_refresh = now
        return self._events

    def get_events_for_symbol(self, symbol: str, window_minutes: int = 10) -> dict:
        events = self.refresh()
        symbol_key = symbol.upper()
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)
        window_end = now + timedelta(minutes=window_minutes)
        active = []
        upcoming = []
        for event in events:
            affects_symbols = [a.upper() for a in event.get("affects", ["ALL"])]
            if "ALL" in affects_symbols or symbol_key in affects_symbols:
                event_time = event.get("event_time")
                if event_time is None:
                    continue
                if window_start <= event_time <= window_end:
                    active.append({
                        "description": event.get("description"),
                        "impact": event.get("impact"),
                        "event_time": event.get("event_time").isoformat() if isinstance(event.get("event_time"), datetime) else str(event.get("event_time")),
                        "symbol": event.get("symbol"),
                    })
                elif event_time > window_end:
                    upcoming.append({
                        "description": event.get("description"),
                        "impact": event.get("impact"),
                        "event_time": event.get("event_time").isoformat() if isinstance(event.get("event_time"), datetime) else str(event.get("event_time")),
                        "symbol": event.get("symbol"),
                    })
        return {
            "active": active,
            "upcoming": upcoming,
            "in_window": len(active) > 0,
            "source": "mt5",
        }
