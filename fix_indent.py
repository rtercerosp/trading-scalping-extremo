with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'rb') as f:
    content = f.read()

old = b'        # Fallback\r\n        return ["SignalTrendPullback"]\r\n\r\n    def _is_strategy_in_probation'
new = b'    # Fallback\r\n    return ["SignalTrendPullback"]\r\n\r\n    def _is_strategy_in_probation'
content = content.replace(old, new)

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'wb') as f:
    f.write(content)
print('Fixed')