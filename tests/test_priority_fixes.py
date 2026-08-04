import unittest
import tempfile
from queue import Queue
from unittest.mock import Mock, patch

import pandas as pd

from ai.learning_engine import LearningEngine
from ai.strategy_selector import StrategySelector
from data_provider.data_provider import DataProvider
from notifications.properties.properties import TelegramNotificationProperties
from order_executor.break_even_manager import BreakEvenManager
from portfolio.portfolio import Portfolio
from signal_generator.properties.signal_generator_properties import RSIProps
from signal_generator.signals.signal_rsi_mr import SignalRSI
from utils.symbol_utils import get_asset_category, normalize_symbol


class TestPriorityFixes(unittest.TestCase):
    def test_rsi_returns_100_when_there_are_no_losses(self):
        signal = SignalRSI(
            RSIProps(
                timeframe="1min",
                rsi_period=5,
                rsi_upper=70.0,
                rsi_lower=30.0,
                sl_points=100,
                tp_points=100,
            ),
            connector=Mock(),
        )

        result = signal.compute_rsi(pd.Series([1, 2, 3, 4, 5, 6], dtype=float))

        self.assertEqual(result, 100.0)

    def test_rsi_returns_50_when_prices_are_flat(self):
        signal = SignalRSI(
            RSIProps(
                timeframe="1min",
                rsi_period=5,
                rsi_upper=70.0,
                rsi_lower=30.0,
                sl_points=100,
                tp_points=100,
            ),
            connector=Mock(),
        )

        result = signal.compute_rsi(pd.Series([5, 5, 5, 5, 5, 5], dtype=float))

        self.assertEqual(result, 50.0)

    @patch("portfolio.portfolio.mt5.positions_get", return_value=None)
    def test_portfolio_handles_none_positions(self, _mock_positions_get):
        portfolio = Portfolio(magic_number=123)

        self.assertEqual(portfolio.get_open_positions(), tuple())
        self.assertEqual(portfolio.get_strategy_open_positions(), tuple())
        self.assertEqual(
            portfolio.get_number_of_strategy_open_positions_by_symbol("BTCUSDc"),
            {"LONG": 0, "SHORT": 0, "TOTAL": 0},
        )

    @patch("order_executor.break_even_manager.mt5.positions_get", return_value=None)
    def test_break_even_manager_tolerates_none_positions(self, _mock_positions_get):
        connector_mock = Mock()
        connector_mock.get_positions.return_value = tuple()
        manager = BreakEvenManager(
            data_provider=Mock(),
            order_executor=Mock(),
            notification_service=Mock(),
            connector=connector_mock,
        )

        manager.positions_to_monitor[1] = {
            "symbol": "BTCUSDc",
            "entry_price": 100.0,
            "initial_tp": 110.0,
            "signal_type": "BUY",
            "sl_moved_to_breakeven": False,
        }

        manager.check_for_tp_hit_and_move_sl()

        self.assertEqual(manager.positions_to_monitor, {})

    def test_telegram_properties_allow_missing_credentials(self):
        props = TelegramNotificationProperties(token=None, chat_id=None)

        self.assertIsNone(props.token)
        self.assertIsNone(props.chat_id)

    def test_data_provider_invalid_timeframe_returns_empty(self):
        connector = Mock()
        connector.get_latest_closed_bar.return_value = pd.Series(dtype=float)
        connector.get_latest_closed_bars.return_value = pd.DataFrame()
        provider = DataProvider(events_queue=Queue(), symbol_list=["BTCUSDc"], timeframe="bad", connector=connector)

        self.assertTrue(provider.get_latest_closed_bar("BTCUSDc", "bad").empty)
        self.assertTrue(provider.get_latest_closed_bars("BTCUSDc", "bad").empty)

    def test_symbol_normalization_supports_broker_suffixes(self):
        self.assertEqual(normalize_symbol("BTCUSDc"), "BTCUSD")
        self.assertEqual(normalize_symbol("ETHUSD."), "ETHUSD")
        self.assertEqual(normalize_symbol("XAUUSD+"), "XAUUSD")
        self.assertEqual(normalize_symbol("EURUSDc"), "EURUSD")
        self.assertEqual(get_asset_category("XAUUSD+"), "gold")

    @patch("portfolio.portfolio.mt5.positions_get", return_value=tuple())
    def test_portfolio_normalizes_symbol_limits(self, _mock_positions_get):
        portfolio = Portfolio(
            magic_number=123,
            max_positions_per_symbol=5,
            max_positions_by_symbol={"BTCUSD": 1},
        )

        with patch.object(
            portfolio,
            "get_number_of_strategy_open_positions_by_symbol",
            return_value={"LONG": 1, "SHORT": 0, "TOTAL": 1},
        ):
            self.assertFalse(portfolio.can_open_position("BTCUSDc"))

    def test_strategy_selector_uses_normalized_symbol_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            selector = StrategySelector(storage_path=f"{temp_dir}/strategy_scores.json")
            selector.update_strategy_score("BTCUSDc", "SignalSmartMoneyBTC", 15.0)

            stats = selector.get_strategy_stats("BTCUSD")

            self.assertIn("SignalSmartMoneyBTC", stats)
            self.assertEqual(stats["SignalSmartMoneyBTC"]["trades"], 1)

    def test_learning_engine_uses_normalized_symbol_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = LearningEngine(storage_path=f"{temp_dir}/learning_params.json")
            engine.update_params("EURUSDc", profit=12.5, sl_hit=False, tp_hit=True)

            params = engine.get_adaptive_params("EURUSD")

            self.assertEqual(params["total_trades"], 1)
            self.assertGreaterEqual(params["tp_atr_mult"], 2.0)


if __name__ == "__main__":
    unittest.main()
