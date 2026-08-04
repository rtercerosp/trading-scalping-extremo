# QUANTDEMY - https://quantdemy.com - Trading con Python y MetaTrader 5: Crea tu Propio Framework

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime


class CandlePatternAnalyzer:
    @staticmethod
    def analyze_candle_behavior(bars: pd.DataFrame) -> Dict:
        if len(bars) < 20:
            return {"valid": False}

        closes = bars["close"].iloc[-20:]
        highs = bars["high"].iloc[-20:]
        lows = bars["low"].iloc[-20:]
        volumes = bars["volume"].iloc[-20:] if "volume" in bars.columns else pd.Series([0]*20)

        body_sizes = (closes - bars["open"].iloc[-20:]).abs()
        wick_upper = highs - bars[["close", "open"]].max(axis=1).iloc[-20:]
        wick_lower = bars[["close", "open"]].min(axis=1).iloc[-20:] - lows

        avg_body = body_sizes.mean()
        avg_wick_upper = wick_upper.mean()
        avg_wick_lower = wick_lower.mean()

        last_body = body_sizes.iloc[-1]
        last_upper = wick_upper.iloc[-1]
        last_lower = wick_lower.iloc[-1]

        pattern = "neutral"
        if avg_body > 0 and (last_upper > 2 * avg_body or last_lower > 2 * avg_body):
            if last_lower > last_upper and last_lower > avg_body:
                pattern = "bullish_rejection"
            elif last_upper > last_lower and last_upper > avg_body:
                pattern = "bearish_rejection"

        momentum = closes.iloc[-1] - closes.iloc[-5]
        volatility = highs.iloc[-10:].max() - lows.iloc[-10:].min()

        return {
            "valid": True,
            "pattern": pattern,
            "momentum": float(momentum),
            "volatility": float(volatility),
            "avg_body": float(avg_body),
            "avg_wick_upper": float(avg_wick_upper),
            "avg_wick_lower": float(avg_wick_lower),
            "volume_trend": float(volumes.diff().mean()) if len(volumes) > 1 else 0.0,
        }

    @staticmethod
    def classify_market_regime(bars: pd.DataFrame) -> str:
        if len(bars) < 30:
            return "unknown"

        close = bars["close"].iloc[-30:]
        ema_fast = close.ewm(span=10, adjust=False).mean()
        ema_slow = close.ewm(span=20, adjust=False).mean()

        price_change = (close.iloc[-1] - close.iloc[0]) / close.iloc[0] if close.iloc[0] != 0 else 0
        volatility = (bars["high"].iloc[-30:].max() - bars["low"].iloc[-30:].min()) / close.iloc[-1] if close.iloc[-1] != 0 else 0

        if ema_fast.iloc[-1] > ema_slow.iloc[-1] and price_change > 0.01:
            if volatility > 0.05:
                return "strong_bullish"
            return "moderate_bullish"
        elif ema_fast.iloc[-1] < ema_slow.iloc[-1] and price_change < -0.01:
            if volatility > 0.05:
                return "strong_bearish"
            return "moderate_bearish"
        elif volatility < 0.02:
            return "range"
        return "neutral"
