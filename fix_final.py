with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'rb') as f:
    content = f.read()

# Fix ALL blank lines between function end and next method to be at function level (8 spaces)
# Pattern: result = order\n\n        return result  ->  result = order\n        \n        return result
content = content.replace(
    b'            result = order\r\n\r\n        return result',
    b'            result = order\r\n        \r\n        return result'
)

# Also fix the blank line between return and next method
content = content.replace(
    b'        return result\r\n\r\n    def _is_strategy_in_probation',
    b'        return result\r\n    \r\n    def _is_strategy_in_probation'
)

with open(r'C:\TRADING SCARLPING EXTR\brain\trading_brain.py', 'wb') as f:
    f.write(content)
print('Fixed')