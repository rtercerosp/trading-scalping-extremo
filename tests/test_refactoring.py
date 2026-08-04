import unittest
import tempfile
import os
from unittest.mock import Mock, patch

from brain.trade_history_manager import TradeHistoryManager
from brain.performance_tracker import PerformanceTracker
from brain.models import TradeRecord
from portfolio.portfolio import Portfolio


class TestTradeHistoryManager(unittest.TestCase):
    def test_add_and_get_open_trade(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = os.path.join(tmpdir, "trade_history.json")
            manager = TradeHistoryManager(history_file=history_file)

            trade = TradeRecord(
                symbol="BTCUSD",
                signal="LONG",
                entry_price=50000.0,
                sl=49000.0,
                tp1=51000.0,
                tp2=52000.0,
                volume=0.01,
                exit_price=50000.0,
                exit_reason="OPEN",
                profit=0.0,
                strategy="SignalBTCExtreme",
            )
            manager.add_trade(trade)

            open_trade = manager.get_open_trade("BTCUSD")
            self.assertIsNotNone(open_trade)
            self.assertEqual(open_trade.entry_price, 50000.0)
            self.assertEqual(open_trade.strategy, "SignalBTCExtreme")

    def test_mark_trade_closed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = os.path.join(tmpdir, "trade_history.json")
            manager = TradeHistoryManager(history_file=history_file)

            trade = TradeRecord(
                symbol="BTCUSD",
                signal="LONG",
                entry_price=50000.0,
                sl=49000.0,
                tp1=51000.0,
                tp2=52000.0,
                volume=0.01,
                exit_price=50000.0,
                exit_reason="OPEN",
                profit=0.0,
                strategy="SignalBTCExtreme",
            )
            manager.add_trade(trade)
            manager.mark_trade_closed("BTCUSD", 51500.0, "TP1", 150.0, 12345)

            open_trade = manager.get_open_trade("BTCUSD")
            self.assertIsNone(open_trade)

            closed_trade = manager.trade_history[0]
            self.assertEqual(closed_trade.exit_reason, "TP1")
            self.assertEqual(closed_trade.profit, 150.0)
            self.assertEqual(closed_trade.closed_deal_ticket, 12345)

    def test_persists_to_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            history_file = os.path.join(tmpdir, "trade_history.json")
            manager = TradeHistoryManager(history_file=history_file)

            trade = TradeRecord(
                symbol="BTCUSD",
                signal="LONG",
                entry_price=50000.0,
                sl=49000.0,
                tp1=51000.0,
                tp2=52000.0,
                volume=0.01,
                exit_price=50000.0,
                exit_reason="OPEN",
                profit=0.0,
                strategy="SignalBTCExtreme",
            )
            manager.add_trade(trade)
            manager._flush()

            self.assertTrue(os.path.exists(history_file))
            with open(history_file, "r", encoding="utf-8") as f:
                import json
                data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["symbol"], "BTCUSD")


class TestPerformanceTracker(unittest.TestCase):
    def test_update_asset_performance(self):
        tracker = PerformanceTracker()
        tracker.update_asset_performance("BTCUSD", 100.0)
        tracker.update_asset_performance("BTCUSD", -50.0)

        perf = tracker.get_asset_performance("BTCUSD")
        self.assertEqual(perf["total_trades"], 2)
        self.assertEqual(perf["winning_trades"], 1)
        self.assertEqual(perf["losing_trades"], 1)
        self.assertEqual(perf["total_profit"], 50.0)
        self.assertAlmostEqual(perf["win_rate"], 0.5)

    def test_update_strategy_performance(self):
        tracker = PerformanceTracker()
        tracker.update_strategy_performance("BTCUSD", "SignalBTCExtreme", 100.0)
        tracker.update_strategy_performance("BTCUSD", "SignalBTCExtreme", -50.0)

        perf = tracker.get_strategy_performance("BTCUSD", "SignalBTCExtreme")
        self.assertEqual(perf["trades"], 2)
        self.assertEqual(perf["wins"], 1)
        self.assertEqual(perf["losses"], 1)
        self.assertAlmostEqual(perf["win_rate"], 0.5)

    def test_normalize_symbol(self):
        tracker = PerformanceTracker()
        tracker.update_asset_performance("BTCUSDc", 100.0)
        perf = tracker.get_asset_performance("BTCUSD")
        self.assertEqual(perf["total_trades"], 1)


class TestPortfolioLimits(unittest.TestCase):
    @patch("portfolio.portfolio.mt5.positions_get", return_value=None)
    def test_can_open_position_respects_limits(self, _mock_positions_get):
        portfolio = Portfolio(
            magic_number=123,
            max_total_positions=3,
            max_positions_per_symbol=1,
            max_positions_by_symbol={"BTCUSD": 1},
            max_positions_by_category={"crypto": 2},
        )
        self.assertTrue(portfolio.can_open_position("BTCUSD"))


if __name__ == "__main__":
    unittest.main()
