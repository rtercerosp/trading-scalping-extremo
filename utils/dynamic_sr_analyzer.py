# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import pandas as pd
from typing import Optional
from datetime import datetime


class DynamicSRAnalyzer:
    def __init__(self, lookback: int = 50, peak_distance: int = 3, tolerance_pct: float = 0.0015, timeframe: str = "5min"):
        self.lookback = max(lookback, 20)
        self.timeframe = timeframe
        self.peak_distance = max(peak_distance, 1)
        self.tolerance_pct = max(tolerance_pct, 0.0001)
        self._apply_timeframe_overrides()

    def _apply_timeframe_overrides(self) -> None:
        tf = (self.timeframe or "").lower()
        if tf in {"15min", "30min", "1h", "4h"}:
            self.peak_distance = max(self.peak_distance, 4)
            self.tolerance_pct = max(self.tolerance_pct, 0.003)
        elif tf in {"daily", "1d", "1w"}:
            self.peak_distance = max(self.peak_distance, 6)
            self.tolerance_pct = max(self.tolerance_pct, 0.006)

    @staticmethod
    def _find_peaks_and_valleys(series: pd.Series, distance: int) -> tuple[pd.Series, pd.Series]:
        peaks = pd.Series(index=series.index, dtype=float)
        valleys = pd.Series(index=series.index, dtype=float)
        values = series.values
        for i in range(distance, len(values) - distance):
            window = values[i - distance: i + distance + 1]
            if values[i] == max(window):
                peaks.iloc[i] = values[i]
            elif values[i] == min(window):
                valleys.iloc[i] = values[i]
        return peaks, valleys

    def analyze(self, bars: pd.DataFrame) -> dict:
        if bars.empty or len(bars) < self.lookback:
            return {"support_levels": [], "resistance_levels": [], "current_price": None}

        recent = bars.iloc[-self.lookback:]
        highs = recent["high"]
        lows = recent["low"]
        closes = recent["close"]

        resistance_peaks, support_valleys = self._find_peaks_and_valleys(highs, self.peak_distance)
        _, resistance_valleys = self._find_peaks_and_valleys(lows, self.peak_distance)
        support_peaks, _ = self._find_peaks_and_valleys(lows, self.peak_distance)

        resistance_levels = []
        support_levels = []

        for value in resistance_peaks.dropna().tolist():
            resistance_levels.append({"price": float(value), "type": "high", "touches": 1})
        for value in support_valleys.dropna().tolist():
            support_levels.append({"price": float(value), "type": "low", "touches": 1})
        for value in resistance_valleys.dropna().tolist():
            support_levels.append({"price": float(value), "type": "low", "touches": 1})
        for value in support_peaks.dropna().tolist():
            resistance_levels.append({"price": float(value), "type": "high", "touches": 1})

        resistance_levels = self._merge_levels(resistance_levels)
        support_levels = self._merge_levels(support_levels)

        current_price = float(closes.iloc[-1])
        resistance_levels = [lvl for lvl in resistance_levels if lvl["price"] > current_price]
        support_levels = [lvl for lvl in support_levels if lvl["price"] < current_price]

        resistance_levels.sort(key=lambda x: x["price"])
        support_levels.sort(key=lambda x: x["price"], reverse=True)

        return {
            "support_levels": support_levels[:5],
            "resistance_levels": resistance_levels[:5],
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
        }

    def _merge_levels(self, levels: list[dict]) -> list[dict]:
        if not levels:
            return []
        levels.sort(key=lambda x: x["price"])
        merged = []
        current = dict(levels[0])
        for level in levels[1:]:
            if abs(level["price"] - current["price"]) / max(abs(current["price"]), 1e-9) <= self.tolerance_pct:
                current["price"] = (current["price"] * current["touches"] + level["price"]) / (current["touches"] + 1)
                current["touches"] += 1
            else:
                merged.append(current)
                current = dict(level)
        merged.append(current)
        merged.sort(key=lambda x: (x["touches"], x["price"]), reverse=True)
        return merged
