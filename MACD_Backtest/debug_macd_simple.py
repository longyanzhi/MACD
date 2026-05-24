"""简化调试脚本：检查 MACD 计算"""
import sys
sys.path.insert(0, r'/MACD_Stock_Strategy')

from database import load_all_stock_data
from macd_calculator import calculate_macd, TALIB_AVAILABLE
import pandas as pd
import numpy as np

print(f"TALIB_AVAILABLE: {TALIB_AVAILABLE}")

# 加载数据
stock_data = load_all_stock_data('2026-01-23', '2026-04-23')
df = stock_data['000601.SZ'].reset_index(drop=True)

print(f"\n原始数据 (前5行):")
print(df[['trade_date', 'close_price']].head())

print(f"\nclose_price 类型: {df['close_price'].dtype}")
print(f"close_price 是否有 NaN: {df['close_price'].isna().any()}")

# 测试 EMA 计算
prices = df['close_price'].astype(float)
print(f"\n价格数据: {prices.values[:5]}")

ema_fast = prices.ewm(span=12, adjust=False).mean()
ema_slow = prices.ewm(span=26, adjust=False).mean()
diff = ema_fast - ema_slow

print(f"\nEMA12 (前5个值): {ema_fast.values[:5]}")
print(f"EMA26 (前5个值): {ema_slow.values[:5]}")
print(f"DIFF (前5个值): {diff.values[:5]}")

# 完整 MACD 计算
print("\n--- 调用 calculate_macd ---")
result = calculate_macd(df.copy(), price_column='close_price')
print(f"\n结果 (前10行):")
print(result[['trade_date', 'close_price', 'DIFF', 'DEA', 'MACD']].head(10))

print(f"\n结果 (最后5行):")
print(result[['trade_date', 'close_price', 'DIFF', 'DEA', 'MACD']].tail(5))
