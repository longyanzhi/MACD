# -*- coding: utf-8 -*-
path = r"C:\Users\35223\MACD\MACD_Stock_Strategy\macd_auto_trader.ahk"
with open(path, "rb") as f:
    data = f.read()

old1 = b'= "\x22\x22\x22\x22)'
new1 = b'= Chr(34))'
old2 = b'= "\x22\x22\x22\x22) {'
new2 = b'= Chr(34)) {'

count = 0
data_fixed = data.replace(old1, new1)
if data_fixed != data:
    count += 1
    print("Fixed pattern 1")

data_fixed2 = data_fixed.replace(old2, new2)
if data_fixed2 != data_fixed:
    count += 1
    print("Fixed pattern 2")

if count > 0:
    with open(path, "wb") as f:
        f.write(data_fixed2)
    print(f"Wrote {count} fix(es)")
else:
    print("No patterns found")
