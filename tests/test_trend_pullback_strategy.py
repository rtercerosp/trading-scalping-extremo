import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from events.events import DataEvent
from signal_generator.properties.signal_generator_properties import TrendPullbackProps
from signal_generator.signals.signal_trend_pullback import SignalTrendPullback


def make_data_event(symbol: str) -> DataEvent:
    return DataEvent(symbol=symbol, data=pd.Series({"close": 100.0}))


class TestTrendPullbackStrategy(unittest.TestCase):
    def setUp(self):
        connector_mock = Mock()
        connector_mock.get_symbol_info.return_value = SimpleNamespace(point=0.01, trade_stops_level=10)
        self.strategy = SignalTrendPullback(
            TrendPullbackProps(
                entry_timeframe="15min",
                trend_timeframe="1h",
                trend_fast_period=3,
                trend_slow_period=5,
                setup_ema_period=3,
                rsi_period=3,
                rsi_bull_threshold=55.0,
                rsi_bear_threshold=45.0,
                atr_period=3,
                sl_atr_mult=1.5,
                tp_atr_mult=3.0,
            ),
            connector=connector_mock,
        )
        self.portfolio = Mock()
        self.portfolio.magic = 20260728
        self.order_executor = Mock()

    def test_generates_buy_signal_when_all_long_conditions_align(self):
        entry_bars = pd.DataFrame(
            {
                "open": [100, 101, 102, 101, 102, 104],
                "high": [101, 102, 103, 102, 103, 106],
                "low": [99, 100, 101, 100, 101, 103],
                "close": [100, 101, 102, 101, 102, 105],
                "tickvol": [1, 1, 1, 1, 1, 1],
                "vol": [1, 1, 1, 1, 1, 1],
                "spread": [1, 1, 1, 1, 1, 1],
            }
        )
        trend_bars = pd.DataFrame(
            {
                "open": [90, 92, 94, 96, 98, 100],
                "high": [91, 93, 95, 97, 99, 101],
                "low": [89, 91, 93, 95, 97, 99],
                "close": [90, 92, 94, 96, 98, 100],
                "tickvol": [1, 1, 1, 1, 1, 1],
                "vol": [1, 1, 1, 1, 1, 1],
                "spread": [1, 1, 1, 1, 1, 1],
            }
        )

        data_provider = Mock()
        data_provider.get_latest_closed_bars.side_effect = (
            lambda symbol, timeframe, num_bars: entry_bars if timeframe == "15min" else trend_bars
        )
        data_provider.get_latest_tick.return_value = {"ask": 105.1, "bid": 104.9}
        self.portfolio.get_number_of_strategy_open_positions_by_symbol.return_value = {
            "LONG": 0,
            "SHORT": 0,
            "TOTAL": 0,
        }

        signal = self.strategy.generate_signal(
            make_data_event("BTCUSDc"),
            data_provider,
            self.portfolio,
            self.order_executor,
        )

        self.assertIsNotNone(signal)
        self.assertEqual(signal.signal, "BUY")
        self.assertLess(signal.sl, 105.1)
        self.assertGreater(signal.tp, 105.1)

    def test_returns_none_when_trend_filter_is_bearish_for_long_case(self):
        entry_bars = pd.DataFrame(
            {
                "open": [100, 101, 102, 101, 102, 104],
                "high": [101, 102, 103, 102, 103, 106],
                "low": [99, 100, 101, 100, 101, 103],
                "close": [100, 101, 102, 101, 102, 105],
                "tickvol": [1, 1, 1, 1, 1, 1],
                "vol": [1, 1, 1, 1, 1, 1],
                "spread": [1, 1, 1, 1, 1, 1],
            }
        )
        trend_bars = pd.DataFrame(
            {
                "open": [100, 99, 98, 97, 96, 95],
                "high": [101, 100, 99, 98, 97, 96],
                "low": [99, 98, 97, 96, 95, 94],
                "close": [100, 99, 98, 97, 96, 95],
                "tickvol": [1, 1, 1, 1, 1, 1],
                "vol": [1, 1, 1, 1, 1, 1],
                "spread": [1, 1, 1, 1, 1, 1],
            }
        )

        data_provider = Mock()
        data_provider.get_latest_closed_bars.side_effect = (
            lambda symbol, timeframe, num_bars: entry_bars if timeframe == "15min" else trend_bars
        )
        data_provider.get_latest_tick.return_value = {"ask": 105.1, "bid": 104.9}
        self.portfolio.get_number_of_strategy_open_positions_by_symbol.return_value = {
            "LONG": 0,
            "SHORT": 0,
            "TOTAL": 0,
        }

        signal = self.strategy.generate_signal(
            make_data_event("BTCUSDc"),
            data_provider,
            self.portfolio,
            self.order_executor,
        )

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
