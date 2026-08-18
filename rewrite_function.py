import sys

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'rb') as f:
    content = f.read()

start_idx = content.find(b'def get_strategy_recommendation(self, symbol: str, asset_category: str) -> list[str]:')
end_idx = content.find(b'    def _is_strategy_in_probation', start_idx)

if start_idx == -1:
    print('Start not found')
    sys.exit(1)
if end_idx == -1:
    print('End not found')
    sys.exit(1)

print(f'Replacing from {start_idx} to {end_idx}')

new_tail = b'''def get_strategy_recommendation(self, symbol: str, asset_category: str) -> list[str]:
        symbol_key = self._symbol_key(symbol)
        available = [s.__class__.__name__ for s in getattr(self, '_current_strategies', [])]
        available = [name for name in available if not self._is_strategy_in_probation(symbol_key, name)]

        if not available:
            return []

        # 1. Cooldown strategy boost (found during circuit breaker optimization)
        if hasattr(self, "_cooldown_strategy_boost") and symbol_key in self._cooldown_strategy_boost:
            boosted = self._cooldown_strategy_boost[symbol_key]
            if boosted in available:
                remaining = [name for name in available if name != boosted]
                logging.info("STRAT REC: %s using cooldown-boosted strategy %s", symbol_key, boosted)
                return [boosted] + remaining

        # 2. Configured primary strategies
        configured = getattr(config, "ASSET_PRIMARY_STRATEGIES", {}).get(symbol_key, [])
        configured = [name for name in configured if name in available]
        if configured:
            remaining = [name for name in available if name not in configured]
            return configured + remaining

        if self.ai_enabled and hasattr(self, 'ai') and self.ai is not None:
            try:
                primary = self.ai.select_strategy(symbol_key, available)
                if primary in available:
                    remaining = [name for name in available if name != primary]
                    order = [primary]
                    if asset_category == "gold":
                        order.extend([name for name in remaining if name in ("SignalTrendPullback", "SignalBreakout", "SignalFibScalp", "SignalRSI", "SignalMACrossover")])
                    elif asset_category == "crypto":
                        order.extend([name for name in remaining if name in ("SignalMomentum", "SignalBreakout", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalBTCStructureBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover")])
                    else:
                        order.extend([name for name in remaining if name in ("SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover", "SignalEURUSDExtreme", "SignalGBPExtreme", "SignalUSDJPExtreme")])
                    order.extend([name for name in remaining if name not in order])
                    return order
            except Exception as e:
                logging.error("BRAIN: Error seleccionando estrategia para %s: %s", symbol_key, e, exc_info=True)

        strat_perf = self.strategy_performance.get(symbol_key, {})
        if strat_perf:
            def strategy_score(item):
                stats = item[1]
                trades = stats.get("trades", 0)
                if trades < 5:
                    return 0.0
                win_rate = stats.get("win_rate", 0.0)
                profit_factor = stats.get("gross_profit", 0.0) / stats.get("gross_loss", 0.0) if stats.get("gross_loss", 0.0) > 0 else (float('inf') if stats.get("gross_profit", 0.0) > 0 else 0.0)
                profit = stats.get("profit", 0.0)
                if getattr(config, "STRATEGY_VERSION", "") == "V10_ZERO_LOSS_SCALPING":
                    return win_rate * 0.6 + min(profit_factor, 4.0) * 0.3 + min(trades / 50.0, 1.0) * 0.1
                return win_rate * 0.4 + min(profit_factor, 3.0) * 0.3 + min(trades / 50.0, 1.0) * 0.3

            ranked = sorted(strat_perf.items(), key=strategy_score, reverse=True)
            best_strategy = ranked[0][0] if ranked else None
            if best_strategy and best_strategy in available:
                order = [best_strategy]
                order.extend([name for name in available if name != best_strategy])
                return order

        perf = self.asset_performance.get(symbol_key, {})
        win_rate = perf.get("win_rate", 0.0)
        total_trades = perf.get("total_trades", 0)

        if total_trades < self.min_trades_for_learning:
            if asset_category == "gold":
                default_by_category = ["SignalXAUExtreme", "SignalFibScalp", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            elif asset_category == "crypto":
                default_by_category = ["SignalFibScalp", "SignalSmartMoneyETH", "SignalMomentum", "SignalBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
            else:
                default_by_category = ["SignalEURUSDExtreme", "SignalSmartMoneyEURUSD", "SignalFibScalp", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            filtered = [name for name in default_by_category if name in available]
            if filtered:
                return filtered
            return available

        # Win-rate based strategy selection
        if win_rate > 0.6:
            if asset_category == "gold":
                preferred = ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            elif asset_category == "crypto":
                preferred = ["SignalMomentum", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalBreakout", "SignalBTCStructureBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
            else:
                preferred = ["SignalEURUSDExtreme", "SignalGBPExtreme", "SignalUSDJPExtreme", "SignalSmartMoneyEURUSD", "SignalMomentum", "SignalBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
        elif win_rate > 0.4:
            if asset_category == "gold":
                preferred = ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            elif asset_category == "crypto":
                preferred = ["SignalMomentum", "SignalBreakout", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
            else:
                preferred = ["SignalEURUSDExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover", "SignalGBPExtreme", "SignalUSDJPExtreme", "SignalSmartMoneyEURUSD"]
        else:
            if asset_category == "gold":
                preferred = ["SignalXAUExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover"]
            elif asset_category == "crypto":
                preferred = ["SignalMomentum", "SignalSmartMoneyBTC", "SignalSmartMoneyETH", "SignalBreakout", "SignalBTCStructureBreakout", "SignalETHStructureBreakout", "SignalTrendPullback", "SignalRSI", "SignalMACrossover"]
            else:
                preferred = ["SignalEURUSDExtreme", "SignalTrendPullback", "SignalBreakout", "SignalRSI", "SignalMACrossover", "SignalSmartMoneyEURUSD", "SignalGBPExtreme", "SignalUSDJPExtreme"]
        
        if available:
            order = [name for name in preferred if name in available]
            order.extend([name for name in available if name not in order])
            return order

        return ["SignalTrendPullback"]

    def _is_strategy_in_probation(self, symbol_key: str, strategy_name: str) -> bool:'''

# Replace the function
new_content = content[:start_idx] + new_tail + content[end_idx + len(b'    def _is_strategy_in_probation(self, symbol_key: str, strategy_name: str) -> bool:'):]

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'wb') as f:
    f.write(new_content)

print('Rewrote function')