from utils.utils import Utils


class TradeRecord:
    def __init__(self, symbol: str, signal: str, entry_price: float, sl: float, tp1: float, tp2: float,
                 volume: float, exit_price: float, exit_reason: str, profit: float, strategy: str, deal_ticket: int = 0, position_ticket: int = 0, closed_deal_ticket: int = 0):
        self.symbol = symbol
        self.signal = signal
        self.entry_price = entry_price
        self.sl = sl
        self.tp1 = tp1
        self.tp2 = tp2
        self.volume = volume
        self.exit_price = exit_price
        self.exit_reason = exit_reason
        self.profit = profit
        self.strategy = strategy
        self.deal_ticket = deal_ticket
        self.position_ticket = position_ticket
        self.closed_deal_ticket = closed_deal_ticket
        self.timestamp = Utils.dateprint()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal": self.signal,
            "entry_price": self.entry_price,
            "sl": self.sl,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "volume": self.volume,
            "exit_price": self.exit_price,
            "exit_reason": self.exit_reason,
            "profit": self.profit,
            "strategy": self.strategy,
            "deal_ticket": self.deal_ticket,
            "position_ticket": self.position_ticket,
            "closed_deal_ticket": self.closed_deal_ticket,
            "timestamp": self.timestamp,
        }
