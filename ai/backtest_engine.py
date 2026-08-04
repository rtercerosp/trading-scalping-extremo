# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import json
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

import pandas as pd
import MetaTrader5 as mt5

from logging import getLogger
from signal_generator.signal_generator import SignalGenerator
from signal_generator.properties.signal_generator_properties import (
    SmartMoneySignalProps,
    TrendPullbackProps,
    RSIProps,
    MACrossoverProps,
)
from portfolio.portfolio import Portfolio
from position_sizer.position_sizers.fixed_size_position_sizer import FixedSizePositionSizer
from risk_manager.risk_managers.max_leverage_factor_risk_manager import MaxLeverageFactorRiskManager
from order_executor.order_executor import OrderExecutor
from platform_connector.platform_connector import PlatformConnector
from data_provider.data_provider import DataProvider
from utils.utils import Utils
from utils.symbol_utils import normalize_symbol
import config

logger = getLogger(__name__)

class BacktestResult:
    def __init__(self, symbol: str, strategy_name: str):
        self.symbol = symbol
        self.strategy_name = strategy_name
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.gross_profit = 0.0
        self.gross_loss = 0.0
        self.total_profit = 0.0
        self.signals_generated = 0
        self.signals_filtered = 0

    def record_signal(self) -> None:
        self.signals_generated += 1

    def record_filtered(self) -> None:
        self.signals_filtered += 1

    def record_trade(self, profit: float) -> None:
        self.trades += 1
        self.total_profit += profit
        if profit > 0:
            self.wins += 1
            self.gross_profit += profit
        else:
            self.losses += 1
            self.gross_loss += abs(profit)

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades > 0 else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss > 0:
            return self.gross_profit / self.gross_loss
        return float('inf') if self.gross_profit > 0 else 0.0

    @property
    def expectancy(self) -> float:
        return self.total_profit / self.trades if self.trades > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "score": self._compute_score(),
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "profit": self.total_profit,
            "gross_profit": self.gross_profit,
            "gross_loss": self.gross_loss,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "expectancy": self.expectancy,
            "signals_generated": self.signals_generated,
            "signals_filtered": self.signals_filtered,
            "last_used": datetime.now().isoformat(),
        }

    def _compute_score(self) -> float:
        win_rate_score = self.win_rate * 50
        pf_score = min(self.profit_factor, 4.0) * 12.5
        trades_score = min(self.trades / 20.0, 5.0) * 5
        expectancy_score = max(min(self.expectancy * 2.0, 20.0), -20.0)
        return win_rate_score + pf_score + trades_score + expectancy_score


class BacktestEngine:
    def __init__(self, symbols: List[str], days_back: int = 180, timeframe: str = "5min"):
        self.symbols = list(symbols)
        self.days_back = days_back
        self.timeframe = timeframe
        self.results: Dict[str, Dict[str, BacktestResult]] = {}
        self.trades_history: List[Dict] = []

    def run(self) -> Dict[str, Dict[str, dict]]:
        print(f"{Utils.dateprint()} - BACKTEST: Iniciando backtest para {self.symbols}")
        print(f"{Utils.dateprint()} - BACKTEST: Dias historicos: {self.days_back}, Timeframe: {self.timeframe}")

        if not mt5.initialize():
            print(f"{Utils.dateprint()} - BACKTEST: Error inicializando MT5: {mt5.last_error()}")
            return {}

        try:
            for symbol in self.symbols:
                self._run_symbol_backtest(symbol)
        finally:
            mt5.shutdown()

        return self._serialize_results()

    def _run_symbol_backtest(self, symbol: str) -> None:
        print(f"\n{Utils.dateprint()} - BACKTEST: Procesando {symbol}")
        symbol_key = normalize_symbol(symbol)

        mtf_timeframe = "30min" if symbol_key in ("BTCUSD", "ETHUSD", "XAUUSD") else "15min"
        etf_timeframe = "15min" if symbol_key in ("BTCUSD", "ETHUSD", "XAUUSD") else "5min"

        bars = self._get_historical_bars(symbol, etf_timeframe, self.days_back)
        if bars is None or bars.empty:
            print(f"{Utils.dateprint()} - BACKTEST: Sin datos para {symbol}")
            return

        trend_bars = self._get_historical_bars(symbol, mtf_timeframe, self.days_back)
        if trend_bars is None or trend_bars.empty:
            trend_bars = bars.copy()

        extra_timeframes = {}
        if symbol_key in ("BTCUSD", "ETHUSD"):
            extra_5min = self._get_historical_bars(symbol, "5min", self.days_back)
            if extra_5min is not None and not extra_5min.empty:
                extra_timeframes["5min"] = extra_5min
        if symbol_key == "EURUSD":
            extra_1min = self._get_historical_bars(symbol, "1min", self.days_back)
            if extra_1min is not None and not extra_1min.empty:
                extra_timeframes["1min"] = extra_1min
        if symbol_key == "XAUUSD":
            extra_5min_xau = self._get_historical_bars(symbol, "5min", self.days_back)
            if extra_5min_xau is not None and not extra_5min_xau.empty:
                extra_timeframes["5min"] = extra_5min_xau

        connector = self._create_mock_connector(symbol, bars)
        data_provider = DataProvider(
            events_queue=None,
            symbol_list=[symbol],
            timeframe=etf_timeframe,
            connector=connector,
        )

        portfolio = Portfolio(
            magic_number=999999,
            max_total_positions=999,
            max_positions_per_symbol=99,
        )
        portfolio.positions = []

        from position_sizer.properties.position_sizer_properties import FixedSizingProps
        position_sizer = FixedSizePositionSizer(properties=FixedSizingProps(volume=0.01))
        from risk_manager.risk_managers.max_leverage_factor_risk_manager import MaxLeverageFactorRiskManager
        from risk_manager.properties.risk_manager_properties import MaxLeverageFactorRiskProps
        risk_manager = MaxLeverageFactorRiskManager(
            properties=MaxLeverageFactorRiskProps(max_leverage_factor=config.RISK_MAX_LEVERAGE_FACTOR),
            notification_service=None,
            connector=connector,
        )
        order_executor = OrderExecutor(
            events_queue=None,
            portfolio=portfolio,
            notification_service=None,
            connector=connector,
        )

        extreme_params = getattr(config, "EXTREME_SCALPING_PARAMS", {}).get(symbol_key, {})
        default_sl_atr_mult = config.LEARNING_DEFAULT_SL_ATR_MULT
        default_tp_atr_mult = config.LEARNING_DEFAULT_TP_ATR_MULT
        if extreme_params and extreme_params.get("enabled", False):
            default_sl_atr_mult = extreme_params.get("sl_atr_mult", default_sl_atr_mult)
            default_tp_atr_mult = extreme_params.get("tp_atr_mult", default_tp_atr_mult)

        signal_props = SmartMoneySignalProps(
            entry_timeframe=etf_timeframe,
            trend_timeframe=mtf_timeframe,
            trend_fast_period=10,
            trend_slow_period=20,
            ema_fast_period=9,
            ema_slow_period=21,
            rsi_period=14,
            rsi_bull_threshold=52.0,
            rsi_bear_threshold=48.0,
            macd_fast=12,
            macd_slow=26,
            macd_signal=9,
            fvg_lookback=20,
            fib_lookback=30,
            atr_period=14,
            sl_atr_mult=default_sl_atr_mult,
            tp_atr_mult=default_tp_atr_mult,
            min_liquidity_gap_points=0.0,
            use_fibonacci=True,
            use_fvg=True,
            use_macd=True,
        )
        trend_props = TrendPullbackProps(
            entry_timeframe=etf_timeframe,
            trend_timeframe=mtf_timeframe,
            trend_fast_period=10,
            trend_slow_period=20,
            setup_ema_period=21,
            rsi_period=14,
            rsi_bull_threshold=52.0,
            rsi_bear_threshold=48.0,
            atr_period=14,
            sl_atr_mult=default_sl_atr_mult,
            tp_atr_mult=default_tp_atr_mult,
        )
        rsi_props = RSIProps(
            timeframe=etf_timeframe,
            rsi_period=14,
            rsi_upper=70.0,
            rsi_lower=30.0,
            sl_points=100,
            tp_points=200,
        )
        ma_props = MACrossoverProps(
            timeframe=etf_timeframe,
            fast_period=9,
            slow_period=21,
        )

        signal_gen = SignalGenerator(
            events_queue=None,
            data_provider=data_provider,
            portfolio=portfolio,
            order_executor=order_executor,
            signal_properties=signal_props,
            connector=connector,
            trading_brain=None,
        )

        from signal_generator.signal_generator import (
            SignalSmartMoneyEURUSD, SignalSmartMoneyBTC, SignalSmartMoneyETH,
            SignalTrendPullback, SignalBreakout, SignalMomentum,
            SignalBTCStructureBreakout, SignalETHStructureBreakout,
            SignalRSI, SignalMACrossover, SignalCandlestickPatterns, SignalFibScalp,
            SignalBTCExtreme, SignalEURUSDExtreme,
        )
        strategy_classes = [
            SignalSmartMoneyEURUSD, SignalSmartMoneyBTC, SignalSmartMoneyETH,
            SignalTrendPullback, SignalBreakout, SignalMomentum,
            SignalBTCStructureBreakout, SignalETHStructureBreakout,
            SignalRSI, SignalMACrossover, SignalCandlestickPatterns, SignalFibScalp,
            SignalBTCExtreme, SignalEURUSDExtreme,
        ]

        for strategy_cls in strategy_classes:
            strategy_name = strategy_cls.__name__
            if strategy_name not in self.results.get(symbol_key, {}):
                self.results.setdefault(symbol_key, {})[strategy_name] = BacktestResult(symbol_key, strategy_name)

        from events.events import DataEvent
        for i in range(len(bars)):
            if i < 20:
                continue

            current_bar = bars.iloc[i]
            current_trend_bar = trend_bars.iloc[min(i, len(trend_bars) - 1)]

            data_provider._bars_cache = {
                etf_timeframe: bars.iloc[:i+1],
                mtf_timeframe: trend_bars.iloc[:min(i+1, len(trend_bars))],
                **{tf: extra.iloc[:i+1] for tf, extra in extra_timeframes.items()},
            }

            data_event = DataEvent(symbol=symbol, data=current_bar)

            for strategy_cls in strategy_classes:
                strategy_name = strategy_cls.__name__
                strategy = next((s for s in signal_gen.strategies if isinstance(s, strategy_cls)), None)
                if strategy is None:
                    continue

                try:
                    signal = strategy.generate_signal(
                        data_event,
                        data_provider,
                        portfolio,
                        order_executor,
                        asset_category=normalize_symbol(symbol) in ("BTCUSD", "ETHUSD") and "crypto" or normalize_symbol(symbol) == "XAUUSD" and "gold" or "forex",
                    )
                    if signal is not None:
                        self.results[symbol_key][strategy_name].record_signal()
                        symbol_info = connector.symbol_info_cache.get(symbol)
                        profit = self._simulate_trade(bars, i, signal, symbol_info)
                        if profit is not None:
                            self.results[symbol_key][strategy_name].record_trade(profit)
                    else:
                        continue
                except Exception:
                    logger.warning("BACKTEST: Error generando señal para %s con %s", symbol, strategy_name, exc_info=True)
                    continue

        for strategy_name, result in self.results.get(symbol_key, {}).items():
            print(f"{Utils.dateprint()} - BACKTEST: {symbol_key} | {strategy_name}: "
                  f"trades={result.trades}, wr={result.win_rate:.2%}, "
                  f"pf={result.profit_factor:.2f}, profit={result.total_profit:.2f}")

    def _get_historical_bars(self, symbol: str, timeframe: str, days_back: int) -> Optional[pd.DataFrame]:
        try:
            tf_map = {
                "1min": mt5.TIMEFRAME_M1,
                "5min": mt5.TIMEFRAME_M5,
                "15min": mt5.TIMEFRAME_M15,
                "30min": mt5.TIMEFRAME_M30,
                "1h": mt5.TIMEFRAME_H1,
                "4h": mt5.TIMEFRAME_H4,
            }
            mtf = tf_map.get(timeframe, mt5.TIMEFRAME_M5)
            utc_from = datetime.utcnow() - timedelta(days=days_back)
            rates = mt5.copy_rates_from_pos(symbol, mtf, 0, days_back * 24)
            if rates is None or len(rates) == 0:
                return None
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            return df
        except Exception as e:
            logger.error("BACKTEST: Error obteniendo barras históricas para %s (%s): %s", symbol, timeframe, e, exc_info=True)
            return None

    def _create_mock_connector(self, symbol: str, bars: pd.DataFrame) -> PlatformConnector:
        connector = PlatformConnector.__new__(PlatformConnector)
        connector.connected = True
        connector.account_info = {
            "login": 12345678,
            "server": "Quantdemy-Demo",
            "balance": 10000.0,
            "equity": 10000.0,
            "leverage": 2000,
            "currency": "USC",
        }
        connector.symbol_info_cache = {}

        first_close = float(bars['close'].iloc[-1])
        symbol_info = mt5.symbol_info(symbol)
        normalized = normalize_symbol(symbol)
        if symbol_info is None:
            class MockInfo:
                pass
            mock_info = MockInfo()
            if normalized == "BTCUSD":
                mock_info.point = 1.0
                mock_info.trade_stops_level = 10
                mock_info.volume_min = 0.01
                mock_info.volume_max = 100.0
                mock_info.volume_step = 0.01
                mock_info.trade_tick_size = 1.0
                mock_info.trade_tick_value = 1.0
                mock_info.trade_contract_size = 1.0
                mock_info.currency_profit = "USD"
            elif normalized == "ETHUSD":
                mock_info.point = 1.0
                mock_info.trade_stops_level = 10
                mock_info.volume_min = 0.01
                mock_info.volume_max = 100.0
                mock_info.volume_step = 0.01
                mock_info.trade_tick_size = 1.0
                mock_info.trade_tick_value = 1.0
                mock_info.trade_contract_size = 1.0
                mock_info.currency_profit = "USD"
            elif normalized == "XAUUSD":
                mock_info.point = 0.01
                mock_info.trade_stops_level = 20
                mock_info.volume_min = 0.01
                mock_info.volume_max = 100.0
                mock_info.volume_step = 0.01
                mock_info.trade_tick_size = 0.01
                mock_info.trade_tick_value = 1.0
                mock_info.trade_contract_size = 100.0
                mock_info.currency_profit = "USD"
            elif normalized == "EURUSD":
                mock_info.point = 0.00001
                mock_info.trade_stops_level = 5
                mock_info.volume_min = 0.01
                mock_info.volume_max = 100.0
                mock_info.volume_step = 0.01
                mock_info.trade_tick_size = 0.00001
                mock_info.trade_tick_value = 1.0
                mock_info.trade_contract_size = 100000.0
                mock_info.currency_profit = "USD"
            else:
                mock_info.point = 0.01
                mock_info.trade_stops_level = 10
                mock_info.volume_min = 0.01
                mock_info.volume_max = 10.0
                mock_info.volume_step = 0.01
                mock_info.trade_tick_size = 0.01
                mock_info.trade_tick_value = 1.0
                mock_info.trade_contract_size = 1.0
                mock_info.currency_profit = "USD"
        else:
            mock_info = symbol_info

        connector.symbol_info_cache[symbol] = mock_info
        connector._get_symbol_info = lambda s: connector.symbol_info_cache.get(s)

        class MockTick:
            def __init__(self, symbol_info):
                self.ask = float(bars['close'].iloc[-1]) + (getattr(symbol_info, 'trade_stops_level', 0) * getattr(symbol_info, 'point', 0.01))
                self.bid = float(bars['close'].iloc[-1]) - (getattr(symbol_info, 'trade_stops_level', 0) * getattr(symbol_info, 'point', 0.01))
            def _asdict(self):
                return {"ask": self.ask, "bid": self.bid}

        def mock_get_history_deals(from_date, to_date):
            return []

        def mock_get_history_orders(from_date, to_date):
            return []

        def mock_order_send(request):
            return None

        connector.get_history_deals = mock_get_history_deals
        connector.get_history_orders = mock_get_history_orders
        connector.order_send = mock_order_send
        connector.get_symbol_info = lambda s: connector._get_symbol_info(s)
        connector.get_symbol_info_tick = lambda s: MockTick(connector._get_symbol_info(s))
        connector.is_market_open = lambda s: True
        connector.get_market_status = lambda s: {"open": True}

        return connector

    def _serialize_results(self) -> Dict[str, Dict[str, dict]]:
        output = {}
        for symbol, strategies in self.results.items():
            output[symbol] = {}
            for strategy_name, result in strategies.items():
                output[symbol][strategy_name] = result.to_dict()
        return output

    def _simulate_trade(self, bars: pd.DataFrame, entry_idx: int, signal, symbol_info=None) -> Optional[float]:
        try:
            entry_price = float(getattr(signal, 'entry_price', 0) or getattr(signal, 'target_price', 0) or bars['close'].iloc[entry_idx])
            sl = float(getattr(signal, 'sl', 0) or 0)
            tp = float(getattr(signal, 'tp1', 0) or getattr(signal, 'tp2', 0) or 0)
            direction = getattr(signal, 'signal', getattr(signal, 'direction', None))
            if direction is None:
                return None
            direction = str(direction).upper()
            is_buy = direction in ('BUY', 'LONG', '1')

            if entry_price <= 0 or (sl <= 0 and tp <= 0):
                return None

            for j in range(entry_idx + 1, len(bars)):
                high = float(bars['high'].iloc[j])
                low = float(bars['low'].iloc[j])

                if is_buy:
                    if sl > 0 and low <= sl:
                        return self._calculate_profit(entry_price, sl, is_buy, symbol_info)
                    if tp > 0 and high >= tp:
                        return self._calculate_profit(entry_price, tp, is_buy, symbol_info)
                else:
                    if sl > 0 and high >= sl:
                        return self._calculate_profit(entry_price, sl, is_buy, symbol_info)
                    if tp > 0 and low <= tp:
                        return self._calculate_profit(entry_price, tp, is_buy, symbol_info)

            exit_price = float(bars['close'].iloc[-1])
            return self._calculate_profit(entry_price, exit_price, is_buy, symbol_info)
        except Exception as e:
            logger.error("BACKTEST: Error simulando trade para %s: %s", signal.symbol, e, exc_info=True)
            return None

    def _calculate_profit(self, entry_price: float, exit_price: float, is_buy: bool, symbol_info=None) -> float:
        price_diff = (exit_price - entry_price) if is_buy else (entry_price - exit_price)

        if symbol_info is None:
            return price_diff

        tick_size = getattr(symbol_info, 'trade_tick_size', None) or getattr(symbol_info, 'point', 0.01)
        tick_value = getattr(symbol_info, 'trade_tick_value', 1.0)
        volume = 0.01

        if tick_size <= 0:
            return price_diff

        return (price_diff / tick_size) * tick_value * volume

    def save_results(self, path: str = "ai/backtest_results.json") -> None:
        data = self._serialize_results()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"{Utils.dateprint()} - BACKTEST: Resultados guardados en {path}")
        except Exception as e:
            print(f"{Utils.dateprint()} - BACKTEST: Error guardando resultados: {e}")

    def get_best_strategies_by_symbol(self, top_n: int = 3) -> Dict[str, List[str]]:
        best = {}
        for symbol, strategies in self.results.items():
            sorted_strats = sorted(
                strategies.values(),
                key=lambda r: r._compute_score(),
                reverse=True
            )
            best[symbol] = [s.strategy_name for s in sorted_strats[:top_n]]
        return best
