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
        # Research/Market microstructure
        self.session = "unknown"
        self.regime = "unknown"
        self.volatility = 0.0
        self.atr = 0.0
        self.spread = 0.0
        self.volume_profile = 0.0
        self.news_proximity = "none"
        self.trend_strength = 0.0
        self.momentum = 0.0
        self.liquidity_score = 0.0
        self.entry_score = 0.0
        self.exit_score = 0.0
        self.risk = 0.0
        self.reward = 0.0
        self.trade_duration_seconds = 0
        self.mfe_points = 0.0
        self.mae_points = 0.0
        self.slippage_points = 0.0
        self.execution_latency_ms = 0.0
        self.correlation_penalty = 0.0
        self.portfolio_heat = 0.0
        self.capital_before = 0.0
        self.capital_after = 0.0
        self.win = False
        self.model_used = "default"
        self.model_scores = {}
        self.parameter_set = {}
        self.notes = ""

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
            "session": self.session,
            "regime": self.regime,
            "volatility": self.volatility,
            "atr": self.atr,
            "spread": self.spread,
            "volume_profile": self.volume_profile,
            "news_proximity": self.news_proximity,
            "trend_strength": self.trend_strength,
            "momentum": self.momentum,
            "liquidity_score": self.liquidity_score,
            "entry_score": self.entry_score,
            "exit_score": self.exit_score,
            "risk": self.risk,
            "reward": self.reward,
            "trade_duration_seconds": self.trade_duration_seconds,
            "mfe_points": self.mfe_points,
            "mae_points": self.mae_points,
            "slippage_points": self.slippage_points,
            "execution_latency_ms": self.execution_latency_ms,
            "correlation_penalty": self.correlation_penalty,
            "portfolio_heat": self.portfolio_heat,
            "capital_before": self.capital_before,
            "capital_after": self.capital_after,
            "win": self.win,
            "model_used": self.model_used,
            "model_scores": self.model_scores,
            "parameter_set": self.parameter_set,
            "notes": self.notes,
        }
