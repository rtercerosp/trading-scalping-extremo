import json
import os
import logging
import time
from typing import Dict, List, Optional

from brain.models import TradeRecord
from utils.symbol_utils import normalize_symbol

logger = logging.getLogger(__name__)


class TradeHistoryManager:
    def __init__(self, history_file: str = "trade_history.json", flush_interval_seconds: float = 5.0) -> None:
        self.history_file = history_file
        self.trade_history: List[TradeRecord] = []
        self.successful_trades: List[TradeRecord] = []
        self.failed_trades: List[TradeRecord] = []
        self._pending_save = False
        self._last_flush_ts = time.time()
        self._flush_interval_seconds = flush_interval_seconds

    def load(self) -> None:
        if not os.path.exists(self.history_file):
            return
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for record_data in data:
                record = TradeRecord(
                    symbol=record_data["symbol"],
                    signal=record_data["signal"],
                    entry_price=record_data["entry_price"],
                    sl=record_data["sl"],
                    tp1=record_data["tp1"],
                    tp2=record_data["tp2"],
                    volume=record_data["volume"],
                    exit_price=record_data["exit_price"],
                    exit_reason=record_data["exit_reason"],
                    profit=record_data["profit"],
                    strategy=record_data["strategy"],
                    deal_ticket=record_data.get("deal_ticket", 0),
                    position_ticket=record_data.get("position_ticket", 0),
                    closed_deal_ticket=record_data.get("closed_deal_ticket", 0),
                )
                self.trade_history.append(record)
                if record.profit > 0:
                    self.successful_trades.append(record)
                else:
                    self.failed_trades.append(record)
            logger.info("BRAIN: Cargados %s registros de trade history", len(self.trade_history))
        except Exception as e:
            logger.error("BRAIN: Error al cargar trade history: %s", e, exc_info=True)

    def save(self) -> None:
        self._pending_save = True
        now = time.time()
        if now - self._last_flush_ts >= self._flush_interval_seconds:
            self._flush()

    def _flush(self) -> None:
        if not self._pending_save:
            return
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump([record.to_dict() for record in self.trade_history], f, indent=2, ensure_ascii=False)
            self._pending_save = False
            self._last_flush_ts = time.time()
        except Exception as e:
            logger.error("BRAIN: Error al guardar trade history: %s", e, exc_info=True)

    def add_trade(self, trade: TradeRecord) -> None:
        self.trade_history.append(trade)
        if trade.profit > 0:
            self.successful_trades.append(trade)
        else:
            self.failed_trades.append(trade)
        self.save()

    def get_open_trade(self, symbol: str) -> Optional[TradeRecord]:
        symbol_key = normalize_symbol(symbol)
        for record in reversed(self.trade_history):
            if normalize_symbol(record.symbol) == symbol_key and record.exit_reason == "OPEN":
                return record
        return None

    def mark_trade_closed(self, symbol: str, exit_price: float, exit_reason: str, profit: float, closed_deal_ticket: int = 0) -> Optional[TradeRecord]:
        record = self.get_open_trade(symbol)
        if record:
            record.exit_price = exit_price
            record.exit_reason = exit_reason
            record.profit = profit
            record.closed_deal_ticket = closed_deal_ticket
            self.save()
        return record
