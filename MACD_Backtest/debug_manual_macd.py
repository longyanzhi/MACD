"""比较手动和talib的MACD计算"""
import sys
sys.path.insert(0, r'/MACD_Stock_Strategy')

from database import load_all_stock_data
from macd_calculator import calculate_macd_manual
import pandas as pd
import numpy as np

# 加载数据
stock_data = load_all_stock_data('2026-01-23', '2026-04-23')
df = stock_data['000601.SZ'].reset_index(drop=True)

close_prices = df['close_price']

print("=== 手动计算 MACD ===")
diff, dea, macd = calculate_macd_manual(close_prices, fast_period=12, slow_period=26, signal_period=9)

print(f"DIFF 前10个值: {diff.values[:10]}")
print(f"DIFF 最后5个值: {diff.values[-5:]}")
print(f"DIFF 中 NaN 数量: {np.sum(np.isnan(diff.values))}")

# 看看手动计算是否更好
result = df.copy()
result['DIFF'] = diff
result['DEA'] = dea
result['MACD'] = macd

print(f"\n前10行:")
print(result[['trade_date', 'close_price', 'DIFF', 'DEA', 'MACD']].head(10))

print(f"\n最后5行:")
print(result[['trade_date', 'close_price', 'DIFF', 'DEA', 'MACD']].tail(5))
