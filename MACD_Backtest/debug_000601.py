"""调试脚本：检查 000601.SZ 的 MACD 金叉和收益率计算"""
import sys
sys.path.insert(0, r'/MACD_Stock_Strategy')

from database import load_all_stock_data
from macd_calculator import calculate_macd
import pandas as pd
from datetime import datetime

# 设置目标日期
target_date = '2026-04-23'
target_dt = pd.to_datetime(target_date)

# 模拟收益率计算窗口
window_end = target_dt - pd.Timedelta(days=1)
window_start = window_end - pd.Timedelta(days=90)

# 加载更多历史数据用于 MACD 计算（需要额外 60 天预热）
macd_warmup_start = window_start - pd.Timedelta(days=60)
print(f"模拟窗口: {window_start} ~ {window_end}")
print(f"加载历史数据用于 MACD: {macd_warmup_start} ~ {window_end}")

stock_data = load_all_stock_data(macd_warmup_start.strftime("%Y-%m-%d"), target_date)

# 检查 000601.SZ
stock_code = '000601.SZ'
if stock_code not in stock_data:
    print(f"股票 {stock_code} 不在数据中!")
    sys.exit()

df = stock_data[stock_code].reset_index(drop=True)
print(f"\n股票 {stock_code} 数据行数: {len(df)}")
print(f"日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")

# 计算 MACD
df = calculate_macd(df, price_column='close_price')

# 显示 2-3 月的关键数据
print("\n=== 2026年2-3月 MACD 数据 ===")
mask = (df['trade_date'] >= '2026-02-01') & (df['trade_date'] <= '2026-03-10')
key_df = df[mask][['trade_date', 'close_price', 'DIFF', 'DEA', 'MACD']].copy()
key_df['DIFF>DEA'] = key_df['DIFF'] > key_df['DEA']
key_df['MACD下降'] = key_df['MACD'].diff() < 0
print(key_df.to_string())

# 检查 2026-02-24 是否有金叉
print("\n=== 检查 2026-02-24 金叉 ===")
row_0224 = df[df['trade_date'] == '2026-02-24']
if len(row_0224) > 0:
    idx = row_0224.index[0]
    if idx > 0:
        curr = df.iloc[idx]
        prev = df.iloc[idx - 1]
        print(f"前一日: {prev['trade_date']}, DIFF={prev['DIFF']:.4f}, DEA={prev['DEA']:.4f}")
        print(f"当日:   {curr['trade_date']}, DIFF={curr['DIFF']:.4f}, DEA={curr['DEA']:.4f}")
        is_golden = (curr['DIFF'] > 0 and curr['DEA'] > 0 and 
                     curr['DIFF'] > curr['DEA'] and prev['DIFF'] <= prev['DEA'])
        print(f"是否金叉: {is_golden}")
else:
    print("2026-02-24 没有数据")

# 模拟收益率计算
print("\n=== 模拟收益率计算 ===")
window_end = target_dt - pd.Timedelta(days=1)
window_start = window_end - pd.Timedelta(days=90)

mask = (df['trade_date'] >= window_start) & (df['trade_date'] <= window_end)
trade_range = df[mask].copy()

print(f"窗口: {window_start} ~ {window_end}")
print(f"窗口内数据: {len(trade_range)} 行")

# 找金叉
golden_cross_idx = None
for i in range(len(trade_range) - 1, 0, -1):
    current = trade_range.iloc[i]
    prev = trade_range.iloc[i - 1]
    
    if (current['DIFF'] > 0 and current['DEA'] > 0 and
        current['DIFF'] > current['DEA'] and prev['DIFF'] <= prev['DEA']):
        golden_cross_idx = i
        print(f"\n找到金叉: 索引={i}, 日期={current['trade_date']}, DIFF={current['DIFF']:.4f}, DEA={current['DEA']:.4f}")
        break

if golden_cross_idx is None:
    print("窗口内没有找到金叉!")
else:
    buy_price = float(trade_range.iloc[golden_cross_idx]['close_price'])
    print(f"买入价: {buy_price}")
    
    # 找 MACD 下降点
    print("\n金叉后的 MACD 数据:")
    for j in range(golden_cross_idx + 1, min(golden_cross_idx + 20, len(trade_range))):
        current = trade_range.iloc[j]
        prev = trade_range.iloc[j - 1]
        macd_change = "↓" if current['MACD'] < prev['MACD'] else "↑"
        print(f"  {current['trade_date']}: MACD={current['MACD']:.4f} {macd_change}")
        
        if pd.notna(current['MACD']) and pd.notna(prev['MACD']):
            if current['MACD'] < prev['MACD']:
                sell_price = float(current['close_price'])
                return_rate = (sell_price - buy_price) / buy_price * 100
                print(f"\n找到卖出点: 日期={current['trade_date']}, 卖出价={sell_price}")
                print(f"收益率: {return_rate:.2f}%")
                break
