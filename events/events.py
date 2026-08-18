# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

from enum import Enum
from pydantic import BaseModel, Field
import pandas as pd
from typing import Optional
from datetime import datetime

# Definición de los distintos tipos de eventos
class EventType(str, Enum):
    """
    Enumeration class representing different types of events.
    
    Attributes:
        DATA: Represents a data event.
        SIGNAL: Represents a signal event.
        SIZING: Represents a sizing event.
        ORDER: Represents an order event.
        EXECUTION: Represents an execution event.
        PENDING: Represents a pending event.
        NEWS: Represents a news event.
        FVG: Represents a fair value gap event.
    """
    DATA = "DATA"
    SIGNAL = "SIGNAL"
    SIZING = "SIZING"
    ORDER = "ORDER"
    EXECUTION = "EXECUTION"
    PENDING = "PENDING"
    NEWS = "NEWS"
    FVG = "FVG"
    REPORT = "REPORT"

class SignalType(str, Enum):
    """
    Represents the type of a trading signal.
    """
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    """
    Represents the type of an order.
    """
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"

class BaseEvent(BaseModel):
    """
    Base class for all events.
    """
    event_type: EventType

    class Config:
        arbitrary_types_allowed = True

class DataEvent(BaseEvent):
    """
    Represents an event that contains data for a specific symbol.

    Attributes:
        event_type (EventType): The type of the event (always EventType.DATA).
        symbol (str): The symbol associated with the data.
        data (pd.Series): The data associated with the event.
        risk_pct_override (Optional[float]): Optional risk override from news protection.
        higher_tf_bias (str): 1H higher timeframe bias.
        higher_tf_strength (float): 1H bias strength.
        higher_tf_support (float): 1H support level.
        higher_tf_resistance (float): 1H resistance level.
    """
    event_type: EventType = EventType.DATA
    symbol: str
    data: pd.Series
    risk_pct_override: Optional[float] = None
    higher_tf_bias: str = "NEUTRAL"
    higher_tf_strength: float = 0.0
    higher_tf_support: float = 0.0
    higher_tf_resistance: float = 0.0


class SignalEvent(BaseEvent):
    """
    Represents a signal event in the trading system.

    Attributes:
        event_type (EventType): The type of the event.
        symbol (str): The symbol associated with the signal.
        signal (SignalType): The type of signal.
        target_order (OrderType): The type of order to be placed.
        target_price (float): The target price for the order.
        magic_number (int): The magic number associated with the signal.
        sl (float): The stop loss level for the order.
        tp (float): The take profit level for the order.
        tp1 (float): The first take profit level for the order.
        tp2 (float): The second take profit level for the order.
        strategy_name (str): Strategy that generated the signal.
        asset_category (str): Asset category.
        market_regime (str): Market regime at signal time.
        analysis_context (dict): Extra analysis context.
        risk_pct_override (float): Optional risk override.
        quality_score (float): Signal quality score from 0 to 100.
        justification (str): Human-readable justification for the signal.
    """
    event_type: EventType = EventType.SIGNAL
    symbol: str
    signal: SignalType
    target_order: OrderType
    target_price: float
    magic_number: int
    sl: float
    tp: float
    tp1: float = 0.0
    tp2: float = 0.0
    strategy_name: str = "UNKNOWN"
    primary_strategy_name: str = "UNKNOWN"
    asset_category: str = "forex"
    market_regime: str = "unknown"
    analysis_context: dict = Field(default_factory=dict)
    risk_pct_override: float = 0.0
    quality_score: float = 0.0
    justification: str = ""


class SizingEvent(BaseEvent):
    """
    Represents a sizing event.

    Attributes:
        event_type (EventType): The type of the event.
        symbol (str): The symbol associated with the event.
        signal (SignalType): The signal type of the event.
        target_order (OrderType): The target order type of the event.
        target_price (float): The target price of the event.
        magic_number (int): The magic number associated with the event.
        sl (float): The stop loss value of the event.
        tp (float): The take profit value of the event.
        tp1 (float): The first take profit value of the event.
        tp2 (float): The second take profit value of the event.
        volume (float): The volume of the event.
        strategy_name (str): Strategy that generated the signal.
        asset_category (str): Asset category.
        market_regime (str): Market regime at signal time.
        analysis_context (dict): Extra analysis context.
        risk_pct_override (float): Optional risk override.
        quality_score (float): Signal quality score from 0 to 100.
        justification (str): Human-readable justification for the signal.
    """
    event_type: EventType = EventType.SIZING
    symbol: str
    signal: SignalType
    target_order: OrderType
    target_price: float
    magic_number: int
    sl: float
    tp: float
    tp1: float = 0.0
    tp2: float = 0.0
    volume: float
    strategy_name: str = "UNKNOWN"
    primary_strategy_name: str = "UNKNOWN"
    asset_category: str = "forex"
    market_regime: str = "unknown"
    analysis_context: dict = Field(default_factory=dict)
    risk_pct_override: float = 0.0
    quality_score: float = 0.0
    justification: str = ""


class OrderEvent(BaseEvent):
    """
    Represents an order event.

    Attributes:
        event_type (EventType): The type of the event.
        symbol (str): The symbol of the order.
        signal (SignalType): The signal type of the order.
        target_order (OrderType): The target order type.
        target_price (float): The target price of the order.
        magic_number (int): The magic number associated with the order.
        sl (float): The stop loss level of the order.
        tp (float): The take profit level of the order.
        tp1 (float): The first take profit level of the order.
        tp2 (float): The second take profit level of the order.
        volume (float): The volume of the order.
        strategy_name (str): Strategy that generated the signal.
        asset_category (str): Asset category.
        market_regime (str): Market regime at signal time.
        analysis_context (dict): Extra analysis context.
        risk_pct_override (float): Optional risk override.
        quality_score (float): Signal quality score from 0 to 100.
        justification (str): Human-readable justification for the signal.
    """
    event_type: EventType = EventType.ORDER
    symbol: str
    signal: SignalType
    target_order: OrderType
    target_price: float
    magic_number: int
    sl: float
    tp: float
    tp1: float = 0.0
    tp2: float = 0.0
    volume: float
    strategy_name: str = "UNKNOWN"
    primary_strategy_name: str = "UNKNOWN"
    asset_category: str = "forex"
    market_regime: str = "unknown"
    analysis_context: dict = Field(default_factory=dict)
    risk_pct_override: float = 0.0
    quality_score: float = 0.0
    justification: str = ""


class ExecutionEvent(BaseEvent):
    """
    Represents an execution event that occurs when a trade is executed.

    Attributes:
        event_type (EventType): The type of the event (EXECUTION).
        symbol (str): The symbol of the executed trade.
        signal (SignalType): The type of signal that triggered the execution.
        fill_price (float): The price at which the trade was executed.
        fill_time (datetime): The timestamp of the trade execution.
        entry_price (float): The entry price of the position (same as fill_price for market orders).
        initial_sl (float): The initial stop loss set for the position.
        initial_tp (float): The initial take profit set for the position.
        tp1 (float): The first take profit level.
        tp2 (float): The second take profit level.
        volume (float): The volume of the executed trade.
        position_ticket (int): The ticket of the position that was opened or modified.
        strategy_type (str): The type of strategy used for this execution.
        deal_ticket (int): The ticket of the deal that originated this execution.
    """
    event_type: EventType = EventType.EXECUTION
    symbol: str
    signal: SignalType
    fill_price: float
    fill_time: datetime
    entry_price: float
    initial_sl: float
    initial_tp: float
    tp1: float = 0.0
    tp2: float = 0.0
    volume: float
    position_ticket: int
    strategy_type: str = "SCALPING_EXTREME"
    strategy_name: str = "UNKNOWN"
    primary_strategy_name: str = "UNKNOWN"
    asset_category: str = "forex"
    market_regime: str = "unknown"
    analysis_context: dict = Field(default_factory=dict)
    deal_ticket: int = 0
    exit_reason: str = "OPEN"
    risk_pct_override: float = 0.0
    quality_score: float = 0.0
    justification: str = ""


class PlacedPendingOrderEvent(BaseEvent):
    """
    Represents an event for a placed pending order.

    Attributes:
        event_type (EventType): The type of the event (EventType.PENDING).
        symbol (str): The symbol of the order.
        signal (SignalType): The type of signal for the order.
        target_order (OrderType): The type of order to be placed.
        target_price (float): The target price for the order.
        magic_number (int): The magic number associated with the order.
        sl (float): The stop loss level for the order.
        tp (float): The take profit level of the order.
        volume (float): The volume of the order.
    """
    event_type: EventType = EventType.PENDING
    symbol: str
    signal: SignalType
    target_order: OrderType
    target_price: float
    magic_number: int
    sl: float
    tp: float
    volume: float


class ReportEvent(BaseEvent):
    """
    Represents a request/trigger to print an institutional report.
    """
    event_type: EventType = EventType.REPORT
    label: str = "manual"
