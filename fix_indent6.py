with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'rb') as f:
    content = f.read()

# Fix blank lines - they should be at function level (8 spaces) not 0 spaces
content = content.replace(
    b'            return available\r\n\r\n        # Fallback',
    b'            return available\r\n        \r\n        # Fallback'
)
content = content.replace(
    b'        return ["SignalTrendPullback"]\r\n\r\n    def _is_strategy_in_probation',
    b'        return ["SignalTrendPullback"]\r\n        \r\n    def _is_strategy_in_probation'
)

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'wb') as f:
    f.write(content)
print('Fixed')