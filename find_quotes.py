# -*- coding: utf-8 -*-
path = r"C:\Users\35223\MACD\MACD_Stock_Strategy\macd_auto_trader.ahk"
with open(path, 'rb') as f:
    data = f.read()

# Find all lines containing 3+ consecutive 0x22 bytes
lines = data.split(b'\n')
for i, line in enumerate(lines, 1):
    # Check for 3 or more consecutive double-quotes
    count = 0
    for b in line:
        if b == 0x22:
            count += 1
            if count >= 3:
                print(f"Line {i}: {line}")
                print(f"  Hex: {line.hex()}")
                break
        else:
            count = 0
