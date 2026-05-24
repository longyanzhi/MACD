"""调试：使用更长历史数据"""
import sys
sys.path.insert(0, r'/MACD_Stock_Strategy')

from database import load_all_stock_data
from macd_calculator import calculate_macd, find_latest_golden_cross, find_sell_point
import pandas as pd
import numpy as np

# 目标日期
target_date = '2026-04-23'
target_dt = pd.to_datetime(target_date)

# 窗口
window_end = target_dt - pd.Timedelta(days=1)
window_start = window_dt = window_end - pd.Timedelta(days=90)

# 加载更多历史数据用于计算 MACD（需要额外 60 天预热）
macd_warmup_start = window_dt - pd.Timedelta(days=60)  # 比窗口开始早 60 天
print(f"窗口: {window_start} ~ {window_end}")
print(f"MACD 预热需要: {macd_warmup_start} ~ {window_end}")

# 加载数据
stock_data = load_all_stock_data(macd_warmup_start.strftime("%Y-%m-%d"), target_date)

# 检查 000601.SZ
stock_code = '000601.SZ'
df = stock_data[stock_code].reset_index(drop=True)
print(f"\n加载数据行数: {len(df)}")
print(f"日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")

# 计算 MACD
df = calculate_macd(df, price_column='close_price')

# 过滤到窗口范围
window_df = df[(df['trade_date'] >= window_start) & (df['trade_date'] <= window_end)].copy()
print(f"\n窗口内数据行数: {len(window_df)}")

print(f"\n窗口内 MACD 数据:")
print(window_df[['trade_date', 'close_price', 'DIFF', 'DEA', 'MACD']].to_string())

# 找金叉
print("\n=== 查找金叉 ===")
buy_point = find_latest_golden_cross(window_df)
if buy_point:
    print(f"找到金叉: 日期={buy_point['date']}, 价格={buy_point['price']}")
    
    # 找卖出点
    sell_point = find_sell_point(window_df, buy_point['index'])
    if sell_point:
        print(f"找到卖出: 日期={sell_point['date']}, 价格={sell_point['price']}")
        return_rate = (sell_point['price'] - buy_point['price']) / buy_point['price'] * 100
        print(f"收益率: {return_rate:.2f}%")
else:
    print("没有找到金叉")
