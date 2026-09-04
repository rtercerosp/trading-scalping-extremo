import pandas as pd
import numpy as np
from typing import Optional
from datetime import datetime
from scipy.signal import find_peaks


class DynamicSRAnalyzer:
    """
    Dynamic Support/Resistance Analyzer using scipy.signal.find_peaks.
    
    Detects local maxima (peaks/resistance) and local minima (valleys/support) 
    across multiple timeframes for dynamic TP/SL adjustment.
    """
    
    def __init__(
        self, 
        lookback: int = 50, 
        peak_distance: int = 3, 
        prominence_pct: float = 0.001,
        timeframe: str = "5min",
        min_touches: int = 2
    ):
        self.lookback = max(lookback, 20)
        self.timeframe = timeframe
        self.peak_distance = max(peak_distance, 1)
        self.prominence_pct = max(prominence_pct, 0.0001)
        self.min_touches = max(min_touches, 1)
        self._apply_timeframe_overrides()

    def _apply_timeframe_overrides(self) -> None:
        tf = (self.timeframe or "").lower()
        if tf in {"15min", "30min", "1h", "4h"}:
            self.peak_distance = max(self.peak_distance, 4)
            self.prominence_pct = max(self.prominence_pct, 0.003)
        elif tf in {"daily", "1d", "1w"}:
            self.peak_distance = max(self.peak_distance, 6)
            self.prominence_pct = max(self.prominence_pct, 0.006)

    @staticmethod
    def _find_peaks_valleys_scipy(series: pd.Series, distance: int, prominence_pct: float) -> tuple[np.ndarray, np.ndarray]:
        """
        Find peaks and valleys using scipy.signal.find_peaks.
        
        Returns:
            tuple: (peak_indices, valley_indices)
        """
        values = series.values
        if len(values) < distance * 2 + 1:
            return np.array([]), np.array([])
        
        # Calculate prominence based on percentage of price range
        price_range = np.max(values) - np.min(values)
        prominence = max(price_range * prominence_pct, 1e-8)
        
        # Find peaks (resistance levels - local maxima)
        peak_indices, _ = find_peaks(values, distance=distance, prominence=prominence)
        
        # Find valleys (support levels - local minima) by inverting the series
        valley_indices, _ = find_peaks(-values, distance=distance, prominence=prominence)
        
        return peak_indices, valley_indices

    def analyze(self, bars: pd.DataFrame) -> dict:
        """
        Analyze price bars to detect dynamic support and resistance levels.
        
        Args:
            bars: DataFrame with columns ['high', 'low', 'close'] and datetime index
            
        Returns:
            dict with support_levels, resistance_levels, current_price, timestamp
        """
        if bars.empty or len(bars) < self.lookback:
            return {"support_levels": [], "resistance_levels": [], "current_price": None}

        recent = bars.iloc[-self.lookback:]
        highs = recent["high"]
        lows = recent["low"]
        closes = recent["close"]

        # Find peaks in highs (resistance candidates)
        resistance_peaks, _ = self._find_peaks_valleys_scipy(highs, self.peak_distance, self.prominence_pct)
        
        # Find valleys in lows (support candidates)
        _, support_valleys = self._find_peaks_valleys_scipy(lows, self.peak_distance, self.prominence_pct)
        
        # Also check for peaks in lows (failed support -> resistance)
        support_peaks, _ = self._find_peaks_valleys_scipy(lows, self.peak_distance, self.prominence_pct)
        
        # And valleys in highs (failed resistance -> support)
        _, resistance_valleys = self._find_peaks_valleys_scipy(highs, self.peak_distance, self.prominence_pct)

        resistance_levels = []
        support_levels = []

        # Process resistance levels (peaks in highs + valleys in highs)
        for idx in resistance_peaks:
            price = float(highs.iloc[idx])
            resistance_levels.append({"price": price, "type": "high_peak", "touches": 1, "index": int(idx)})
        for idx in resistance_valleys:
            price = float(highs.iloc[idx])
            resistance_levels.append({"price": price, "type": "high_valley", "touches": 1, "index": int(idx)})

        # Process support levels (valleys in lows + peaks in lows)
        for idx in support_valleys:
            price = float(lows.iloc[idx])
            support_levels.append({"price": price, "type": "low_valley", "touches": 1, "index": int(idx)})
        for idx in support_peaks:
            price = float(lows.iloc[idx])
            support_levels.append({"price": price, "type": "low_peak", "touches": 1, "index": int(idx)})

        # Merge nearby levels and count touches
        resistance_levels = self._merge_levels(resistance_levels)
        support_levels = self._merge_levels(support_levels)

        # Filter by minimum touches
        resistance_levels = [lvl for lvl in resistance_levels if lvl["touches"] >= self.min_touches]
        support_levels = [lvl for lvl in support_levels if lvl["touches"] >= self.min_touches]

        current_price = float(closes.iloc[-1])
        
        # Only keep levels on the correct side of current price
        resistance_levels = [lvl for lvl in resistance_levels if lvl["price"] > current_price]
        support_levels = [lvl for lvl in support_levels if lvl["price"] < current_price]

        # Sort: resistance ascending (nearest first), support descending (nearest first)
        resistance_levels.sort(key=lambda x: x["price"])
        support_levels.sort(key=lambda x: x["price"], reverse=True)

        return {
            "support_levels": support_levels[:5],
            "resistance_levels": resistance_levels[:5],
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            "timeframe": self.timeframe,
            "lookback": self.lookback
        }

    def analyze_multi_timeframe(self, bars_dict: dict[str, pd.DataFrame]) -> dict:
        """
        Analyze multiple timeframes and aggregate S/R levels.
        
        Args:
            bars_dict: Dict mapping timeframe -> DataFrame with OHLC data
            
        Returns:
            Aggregated support/resistance levels with timeframe info
        """
        all_support = []
        all_resistance = []
        current_price = None
        
        for tf, bars in bars_dict.items():
            if bars is None or bars.empty:
                continue
                
            # Temporarily set timeframe for this analysis
            original_tf = self.timeframe
            self.timeframe = tf
            self._apply_timeframe_overrides()
            
            result = self.analyze(bars)
            
            if current_price is None:
                current_price = result["current_price"]
            
            # Tag levels with timeframe
            for lvl in result["support_levels"]:
                lvl["timeframe"] = tf
                all_support.append(lvl)
            for lvl in result["resistance_levels"]:
                lvl["timeframe"] = tf
                all_resistance.append(lvl)
            
            # Restore original timeframe
            self.timeframe = original_tf
            self._apply_timeframe_overrides()
        
        # Merge across timeframes
        merged_support = self._merge_levels_multi_tf(all_support)
        merged_resistance = self._merge_levels_multi_tf(all_resistance)
        
        if current_price is not None:
            merged_support = [lvl for lvl in merged_support if lvl["price"] < current_price]
            merged_resistance = [lvl for lvl in merged_resistance if lvl["price"] > current_price]
        
        merged_support.sort(key=lambda x: x["price"], reverse=True)
        merged_resistance.sort(key=lambda x: x["price"])
        
        return {
            "support_levels": merged_support[:5],
            "resistance_levels": merged_resistance[:5],
            "current_price": current_price,
            "timestamp": datetime.now().isoformat(),
            "timeframes_analyzed": list(bars_dict.keys())
        }

    def _merge_levels(self, levels: list[dict]) -> list[dict]:
        """Merge nearby price levels and count touches."""
        if not levels:
            return []
        
        levels.sort(key=lambda x: x["price"])
        merged = []
        current = dict(levels[0])
        
        for level in levels[1:]:
            price_diff_pct = abs(level["price"] - current["price"]) / max(abs(current["price"]), 1e-9)
            if price_diff_pct <= self.prominence_pct * 2:  # Allow slightly wider merge
                current["price"] = (current["price"] * current["touches"] + level["price"]) / (current["touches"] + 1)
                current["touches"] += level["touches"]
                # Track all timeframes if present
                if "timeframe" in level:
                    if "timeframes" not in current:
                        current["timeframes"] = [current.get("timeframe")]
                    if level["timeframe"] not in current["timeframes"]:
                        current["timeframes"].append(level["timeframe"])
            else:
                merged.append(current)
                current = dict(level)
        
        merged.append(current)
        # Sort by touches (strength) then by price
        merged.sort(key=lambda x: (x["touches"], x["price"]), reverse=True)
        return merged

    def _merge_levels_multi_tf(self, levels: list[dict]) -> list[dict]:
        """Merge levels from multiple timeframes, tracking timeframe diversity."""
        if not levels:
            return []
        
        levels.sort(key=lambda x: x["price"])
        merged = []
        current = dict(levels[0])
        current["timeframes"] = [current.get("timeframe")] if "timeframe" in current else []
        
        for level in levels[1:]:
            price_diff_pct = abs(level["price"] - current["price"]) / max(abs(current["price"]), 1e-9)
            if price_diff_pct <= self.prominence_pct * 3:  # Wider merge for multi-TF
                current["price"] = (current["price"] * current["touches"] + level["price"]) / (current["touches"] + 1)
                current["touches"] += level["touches"]
                if "timeframe" in level and level["timeframe"] not in current["timeframes"]:
                    current["timeframes"].append(level["timeframe"])
            else:
                merged.append(current)
                current = dict(level)
                current["timeframes"] = [current.get("timeframe")] if "timeframe" in current else []
        
        merged.append(current)
        # Sort by: 1) number of timeframes (confluence), 2) touches, 3) price
        merged.sort(key=lambda x: (len(x.get("timeframes", [])), x["touches"], x["price"]), reverse=True)
        return merged

    def get_dynamic_tp_sl(
        self, 
        current_price: float, 
        signal_type: str, 
        atr: float,
        atr_multiplier_tp: float = 2.0,
        atr_multiplier_sl: float = 1.0
    ) -> dict:
        """
        Calculate dynamic TP/SL based on detected S/R levels.
        
        Args:
            current_price: Current market price
            signal_type: "BUY" or "SELL"
            atr: Average True Range for fallback
            atr_multiplier_tp: TP multiplier for ATR fallback
            atr_multiplier_sl: SL multiplier for ATR fallback
            
        Returns:
            dict with tp, sl, tp_source, sl_source
        """
        # This would be called after analyze() to get levels
        # For now, return ATR-based levels as fallback
        if signal_type == "BUY":
            tp = current_price + atr * atr_multiplier_tp
            sl = current_price - atr * atr_multiplier_sl
        else:
            tp = current_price - atr * atr_multiplier_tp
            sl = current_price + atr * atr_multiplier_sl
            
        return {
            "tp": tp,
            "sl": sl,
            "tp_source": "atr_fallback",
            "sl_source": "atr_fallback"
        }