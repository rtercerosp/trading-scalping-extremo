with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'rb') as f:
    content = f.read()

content = content.replace(
    b'        return ["SignalTrendPullback"]\r\n        \r\n    def _is_strategy_in_probation',
    b'        return ["SignalTrendPullback"]\r\n    def _is_strategy_in_probation'
)

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'wb') as f:
    f.write(content)
print('Fixed')