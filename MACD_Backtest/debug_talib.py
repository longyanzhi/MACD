"""检查 talib 返回值"""
import sys
sys.path.insert(0, r'/MACD_Stock_Strategy')

from database import load_all_stock_data
import pandas as pd
import numpy as np
import talib

# 加载数据
stock_data = load_all_stock_data('2026-01-23', '2026-04-23')
df = stock_data['000601.SZ'].reset_index(drop=True)

close_prices = df['close_price'].values.astype(np.float64)

print(f"输入价格数据长度: {len(close_prices)}")
print(f"前5个价格: {close_prices[:5]}")

# 调用 talib
diff, dea, macd = talib.MACD(close_prices, fastperiod=12, slowperiod=26, signalperiod=9)

print(f"\ntalib 返回值长度: diff={len(diff)}, dea={len(dea)}, macd={len(macd)}")
print(f"DIFF 前10个值: {diff[:10]}")
print(f"DIFF 最后5个值: {diff[-5:]}")

# 检查是否有 NaN
print(f"\nDIFF 中 NaN 数量: {np.sum(np.isnan(diff))}")
print(f"DEA 中 NaN 数量: {np.sum(np.isnan(dea))}")
print(f"MACD 中 NaN 数量: {np.sum(np.isnan(macd))}")
