import numpy as np
import pandas as pd
import logging
import sys
from pathlib import Path
from typing import Optional
from queue import Queue

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import config
from events.events import SignalEvent, SizingEvent
from data_provider.data_provider import DataProvider
from platform_connector.platform_connector import PlatformConnector
from position_sizer.interfaces.position_sizer_interface import IPositionSizer
from position_sizer.properties.position_sizer_properties import BaseSizingProps
from utils.utils import Utils
from utils.symbol_utils import normalize_symbol
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class KellySizingProps(BaseSizingProps):
    """
    Properties for Kelly Criterion position sizing.

    Attributes:
        risk_pct (float): Base risk percentage (fallback when Kelly is unavailable).
        kelly_fraction (float): Fraction of full Kelly to apply (e.g., 0.25 = 25% Kelly).
        min_win_rate (float): Minimum win rate to enable Kelly calculation.
        min_trades (int): Minimum trades required for statistical validity.
        volatility_lookback (int): Number of periods for volatility estimation.
    """
    risk_pct: float = Field(default=0.015, ge=0.0, le=1.0)
    kelly_fraction: float = Field(default=0.25, ge=0.0, le=1.0)
    min_win_rate: float = Field(default=0.35, ge=0.0, le=1.0)
    min_trades: int = Field(default=30, ge=10)
    volatility_lookback: int = Field(default=20, ge=5)


class KellyCriterionSizer(IPositionSizer):
    """
    Kelly Criterion Position Sizer.

    Dynamically calculates optimal capital allocation based on:
    - Edge (mathematical expectancy)
    - Win probability
    - Current volatility regime
    
    Output is constrained by config.LEARNING_RISK_PCT_MIN and config.LEARNING_RISK_PCT_MAX.
    ENFORCES 1% MAX RISK RULE: Never risks more than 1% of equity per trade.
    """

    # Regla del 1% inviolable
    MAX_RISK_PCT_PER_TRADE = 0.01  # 1%

    def __init__(
        self,
        properties: KellySizingProps,
        connector: PlatformConnector,
        get_strategy_metrics_callback=None,
        portfolio=None,
        max_leverage_factor=None,
        data_provider: Optional[DataProvider] = None,
        events_queue: Optional[Queue] = None
    ):
        self.base_risk_pct = min(properties.risk_pct, self.MAX_RISK_PCT_PER_TRADE)
        self.kelly_fraction = properties.kelly_fraction
        self.min_win_rate = properties.min_win_rate
        self.min_trades = properties.min_trades
        self.volatility_lookback = properties.volatility_lookback
        self.connector = connector
        self.get_strategy_metrics_callback = get_strategy_metrics_callback
        self.portfolio = portfolio
        self.max_leverage_factor = max_leverage_factor or getattr(config, "RISK_MAX_LEVERAGE_FACTOR", None)
        self.data_provider = data_provider
        self.events_queue = events_queue

        self._risk_min = config.LEARNING_RISK_PCT_MIN
        self._risk_max = min(config.LEARNING_RISK_PCT_MAX, self.MAX_RISK_PCT_PER_TRADE)

    def _calculate_kelly_fraction(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        volatility: float
    ) -> float:
        """
        Calculate Kelly fraction with volatility adjustment.

        Kelly formula: f* = (b * p - q) / b
        where b = avg_win / avg_loss, p = win_rate, q = 1 - p

        Volatility adjustment: scale down when volatility is high
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        b = avg_win / avg_loss
        p = win_rate
        q = 1.0 - p

        kelly_raw = (b * p - q) / b

        if kelly_raw <= 0:
            return 0.0

        vol_adjustment = 1.0 / (1.0 + volatility * 10.0)
        kelly_adjusted = kelly_raw * vol_adjustment

        return kelly_adjusted * self.kelly_fraction

    def _get_strategy_metrics(self, symbol: str, strategy: str) -> Optional[dict]:
        """Retrieve strategy metrics from callback or return None."""
        if self.get_strategy_metrics_callback:
            try:
                return self.get_strategy_metrics_callback(symbol, strategy)
            except Exception as e:
                logger.warning("KellySizer: Error getting metrics for %s/%s: %s", symbol, strategy, e)
        return None

    def _estimate_volatility(self, symbol: str, data_provider: DataProvider) -> float:
        """Estimate current volatility using ATR-like measure."""
        try:
            bars = data_provider.get_bars(symbol, count=self.volatility_lookback)
            if bars is None or len(bars) < 5:
                return 0.01

            high = bars['high'].values
            low = bars['low'].values
            close = bars['close'].values

            tr = np.maximum(high[1:] - low[1:], np.abs(high[1:] - close[:-1]), np.abs(low[1:] - close[:-1]))
            atr = np.mean(tr)
            current_price = close[-1]

            return atr / current_price if current_price > 0 else 0.01
        except Exception:
            return 0.01

    def size_signal_with_provider(self, signal_event: SignalEvent, data_provider: DataProvider) -> float:
        """
        Core Kelly sizing logic - calculates volume for a signal.

        Args:
            signal_event: Signal with symbol, direction, SL, TP
            data_provider: Market data provider

        Returns:
            float: Position volume in lots
        """
        risk_pct = self.base_risk_pct
        symbol = signal_event.symbol
        strategy = getattr(signal_event, 'strategy_name', None)

        metrics = None
        if strategy:
            metrics = self._get_strategy_metrics(symbol, strategy)

        if metrics and metrics.get('total_trades', 0) >= self.min_trades:
            win_rate = metrics.get('win_rate', 0.0)
            avg_win = metrics.get('avg_win', 0.0)
            avg_loss = metrics.get('avg_loss', 0.0)

            if win_rate >= self.min_win_rate and avg_win > 0 and avg_loss > 0:
                volatility = self._estimate_volatility(symbol, data_provider)
                kelly_f = self._calculate_kelly_fraction(win_rate, avg_win, avg_loss, volatility)

                if kelly_f > 0:
                    risk_pct = kelly_f
                    logger.info(
                        "KellySizer: %s/%s Kelly=%.4f%% (WR=%.2f%%, AvgWin=%.2f, AvgLoss=%.2f, Vol=%.4f)",
                        symbol, strategy, kelly_f * 100, win_rate * 100, avg_win, avg_loss, volatility
                    )

        if getattr(signal_event, 'risk_pct_override', 0.0) > 0.0:
            risk_pct = signal_event.risk_pct_override

        boost_multiplier = getattr(signal_event, 'boost_multiplier', 1.0)
        if boost_multiplier > 1.0:
            risk_pct *= boost_multiplier
            print(f"{Utils.dateprint()} - BOOST: {symbol} TOP performer - riesgo aumentado x{boost_multiplier:.1f} a {risk_pct:.2%}")

        # REGLA DEL 1% INVIOLABLE: Clampear risk_pct a máximo 1%
        if risk_pct > self.MAX_RISK_PCT_PER_TRADE:
            print(f"{Utils.dateprint()} - KELLY SIZER: ⚠️ risk_pct {risk_pct:.4%} excede límite 1%. Clampeando a {self.MAX_RISK_PCT_PER_TRADE:.2%}")
            risk_pct = self.MAX_RISK_PCT_PER_TRADE

        risk_pct = max(self._risk_min, min(self._risk_max, risk_pct))

        if risk_pct <= 0.0:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): Risk percentage invalid: {risk_pct}")
            return 0.0

        if signal_event.sl <= 0.0:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): Invalid SL: {signal_event.sl}")
            return 0.0

        account_info = self.connector.get_account_info()
        if not account_info:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): No account info")
            return 0.0

        symbol_info = self.connector.get_symbol_info(symbol)
        if not symbol_info:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): No symbol info for {symbol}")
            return 0.0

        last_tick = data_provider.get_latest_tick(symbol)
        if not last_tick:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): No tick for {symbol}")
            return 0.0

        if signal_event.target_order == "MARKET":
            entry_price = last_tick['ask'] if signal_event.signal == "BUY" else last_tick['bid']
        else:
            entry_price = signal_event.target_price

        equity = account_info.equity
        volume_step = symbol_info.volume_step
        tick_size = symbol_info.trade_tick_size
        account_ccy = account_info.currency
        symbol_profit_ccy = symbol_info.currency_profit
        contract_size = symbol_info.trade_contract_size

        tick_value_profit_ccy = contract_size * tick_size
        tick_value_account_ccy = self.connector.convert_currency_amount_to_another_currency(
            tick_value_profit_ccy, symbol_profit_ccy, account_ccy
        )

        max_allowed_volume = getattr(symbol_info, 'volume_max', None)
        if max_allowed_volume is None and self.portfolio is not None:
            max_for_symbol = self.portfolio.max_positions_by_symbol.get(
                normalize_symbol(symbol), getattr(self.portfolio, 'max_positions_per_symbol', 2)
            )
            max_allowed_volume = max(0.01, float(max_for_symbol))

        try:
            price_distance_in_ticks = abs(entry_price - signal_event.sl) / tick_size
            if price_distance_in_ticks < 1:
                print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): SL distance < 1 tick")
                return 0.0

            min_sl_distance_pct = 0.001
            if price_distance_in_ticks * tick_size < entry_price * min_sl_distance_pct:
                price_distance_in_ticks = int(entry_price * min_sl_distance_pct / tick_size)
                if price_distance_in_ticks < 1:
                    price_distance_in_ticks = 1

            price_distance_in_integer_ticksizes = int(price_distance_in_ticks)
            monetary_risk = equity * risk_pct
            volume = monetary_risk / (price_distance_in_integer_ticksizes * tick_value_account_ccy) if tick_value_account_ccy > 0 else 0
            volume = round(volume / volume_step) * volume_step

            if equity > 0 and entry_price > 0 and contract_size > 0:
                notional_value = entry_price * contract_size
                max_notional_pct = getattr(config, "PORTFOLIO_MAX_NOTIONAL_PCT_PER_TRADE", 0.50)
                max_volume_by_equity = equity * max_notional_pct / notional_value
                max_volume_by_equity = max(symbol_info.volume_min, round(max_volume_by_equity / volume_step) * volume_step)
                if max_volume_by_equity < volume:
                    volume = max_volume_by_equity
                    print(f"{Utils.dateprint()} - RISK MGMT: Volumen limitado por notional a {max_volume_by_equity:.4f} lotes para {symbol}")

            if self.max_leverage_factor and equity > 0 and entry_price > 0 and contract_size > 0:
                notional_value = entry_price * contract_size
                max_volume_by_leverage = equity * self.max_leverage_factor / notional_value
                max_volume_by_leverage = max(symbol_info.volume_min, round(max_volume_by_leverage / volume_step) * volume_step)
                if max_volume_by_leverage < volume:
                    volume = max_volume_by_leverage
                    print(f"{Utils.dateprint()} - RISK MGMT: Volumen limitado por leverage max ({self.max_leverage_factor}x) a {max_volume_by_leverage:.4f} lotes para {symbol}")

            if max_allowed_volume is not None and volume > max_allowed_volume:
                volume = max_allowed_volume
                print(f"{Utils.dateprint()} - RISK MGMT: Volumen limitado a {max_allowed_volume} lotes para {symbol}")

            volume_min = getattr(symbol_info, 'volume_min', 0.0)
            if volume_min > 0 and volume < volume_min:
                if max_allowed_volume is not None and volume_min > max_allowed_volume:
                    print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): volume_min > max_allowed_volume for {symbol}")
                    return 0.0
                volume = volume_min
                print(f"{Utils.dateprint()} - WARNING (KellyCriterionSizer): Volumen ajustado a volume_min {volume_min} para {symbol}")

            if boost_multiplier > 1.0:
                volume = round(volume * boost_multiplier / volume_step) * volume_step
                print(f"{Utils.dateprint()} - BOOST: {symbol} TOP performer - volumen aumentado x{boost_multiplier:.1f} a {volume:.4f} lotes")

            # VERIFICACIÓN FINAL: Confirmar riesgo ≤ 1%
            price_distance_in_integer_ticksizes = int(price_distance_in_ticks)
            actual_risk_pct = (price_distance_in_integer_ticksizes * tick_value_account_ccy * volume) / equity if equity > 0 else 0
            if actual_risk_pct > self.MAX_RISK_PCT_PER_TRADE * 1.001:
                print(f"{Utils.dateprint()} - KELLY SIZER: ⚠️ Riesgo real {actual_risk_pct:.4%} > 1%. Ajustando volumen...")
                volume = (equity * self.MAX_RISK_PCT_PER_TRADE) / (price_distance_in_integer_ticksizes * tick_value_account_ccy)
                volume = round(volume / volume_step) * volume_step
            
            final_risk_pct = (price_distance_in_integer_ticksizes * tick_value_account_ccy * volume) / equity if equity > 0 else 0
            print(f"{Utils.dateprint()} - KELLY SIZER: {symbol} Volumen={volume:.4f} lotes | Riesgo={final_risk_pct:.4%} (Máx 1%) | Kelly Risk={risk_pct:.4%} | Equity={equity:.2f}")

            return volume

        except Exception as e:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): {e}")
            return 0.0

    def size_signal(self, signal_event: SignalEvent) -> None:
        """
        Manager-compatible interface expected by TradingDirector.
        Calculates volume and enqueues SizingEvent to events_queue.
        """
        if self.data_provider is None:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): No data_provider set for manager interface")
            return

        if self.events_queue is None:
            print(f"{Utils.dateprint()} - ERROR (KellyCriterionSizer): No events_queue set for manager interface")
            return

        # Calculate volume using the core logic with stored data_provider
        volume = self.size_signal_with_provider(signal_event, self.data_provider)

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


def calculate_kelly_fraction(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    kelly_fraction: float = 0.25,
    volatility: float = 0.01
) -> float:
    """
    Standalone Kelly Criterion calculation for testing/simulation.

    Args:
        win_rate: Probability of winning (0-1)
        avg_win: Average winning trade P&L
        avg_loss: Average losing trade P&L (positive value)
        kelly_fraction: Fraction of full Kelly to apply
        volatility: Current volatility estimate

    Returns:
        float: Optimal risk fraction (0-1)
    """
    if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
        return 0.0

    b = avg_win / avg_loss
    p = win_rate
    q = 1.0 - p

    kelly_raw = (b * p - q) / b

    if kelly_raw <= 0:
        return 0.0

    vol_adjustment = 1.0 / (1.0 + volatility * 10.0)
    return kelly_raw * vol_adjustment * kelly_fraction


if __name__ == '__main__':
    print("=" * 60)
    print("KELLY CRITERION SIZER - SIMULATION WITH REAL TERMINAL DATA")
    print("=" * 60)

    win_rate = 0.4450
    expectancy = -0.0423

    avg_loss = 1.0
    avg_win = (expectancy + (1 - win_rate) * avg_loss) / win_rate if win_rate > 0 else 0.0

    print(f"\nInput Parameters:")
    print(f"  Win Rate: {win_rate:.2%}")
    print(f"  Expectancy: {expectancy:.4f}")
    print(f"  Avg Win (derived): {avg_win:.4f}")
    print(f"  Avg Loss (assumed): {avg_loss:.4f}")
    print(f"  Risk Limits: [{config.LEARNING_RISK_PCT_MIN:.2%}, {config.LEARNING_RISK_PCT_MAX:.2%}]")

    kelly_raw = calculate_kelly_fraction(win_rate, avg_win, avg_loss, kelly_fraction=1.0, volatility=0.015)
    kelly_quarter = calculate_kelly_fraction(win_rate, avg_win, avg_loss, kelly_fraction=0.25, volatility=0.015)
    kelly_half = calculate_kelly_fraction(win_rate, avg_win, avg_loss, kelly_fraction=0.50, volatility=0.015)

    print(f"\nKelly Calculations:")
    print(f"  Full Kelly (1.0x): {kelly_raw:.4f} ({kelly_raw:.2%})")
    print(f"  Half Kelly (0.5x): {kelly_half:.4f} ({kelly_half:.2%})")
    print(f"  Quarter Kelly (0.25x): {kelly_quarter:.4f} ({kelly_quarter:.2%})")

    final_risk = max(config.LEARNING_RISK_PCT_MIN, min(config.LEARNING_RISK_PCT_MAX, kelly_quarter))
    print(f"\nConstrained Risk (Quarter Kelly, clamped): {final_risk:.4f} ({final_risk:.2%})")

    if final_risk <= config.LEARNING_RISK_PCT_MIN:
        print("\n>>> AUDIT RESULT: System correctly reduces exposure to minimum")
        print("    due to negative expectancy (-0.0423) and sub-50% win rate.")
    elif final_risk >= config.LEARNING_RISK_PCT_MAX:
        print("\n>>> AUDIT RESULT: System at maximum risk (unexpected for these metrics)")
    else:
        print(f"\n>>> AUDIT RESULT: System allocates {final_risk:.2%} risk (intermediate)")

    print("\n" + "=" * 60)
    print("SIMULATION COMPLETE")
    print("=" * 60)