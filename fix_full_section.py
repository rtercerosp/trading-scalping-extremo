# Fix the indentation error in trading_brain.py by rewriting the end of get_strategy_recommendation
with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'rb') as f:
    content = f.read()

# Find the problematic section and replace it entirely
# We'll replace from "perf = self.asset_performance.get(symbol_key, {})" to the next method

old_section = b'''        perf = self.asset_performance.get(symbol_key, {})
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
        order = [name for name in preferred if name in available]
        order.extend([name for name in available if name not in order])
        result = order
        return result
    def _is_strategy_in_probation'''

new_section = b'''        # Determine result using single return pattern
        result = None
        
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
                result = filtered
            else:
                result = available
        else:
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
            
            order = [name for name in preferred if name in available]
            order.extend([name for name in available if name not in order])
            result = order

        return result

    def _is_strategy_in_probation'''

content = content.replace(old_section, new_section)

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'wb') as f:
    f.write(content)
print('Replaced section')