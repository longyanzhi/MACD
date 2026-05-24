import sys, os
sys.path.insert(0, r'/MACD_Stock_Strategy')
import pandas as pd
from calendar import monthrange
from database import execute_with_retry
from macd_calculator import calculate_macd
from monthly_backtest import MonthlyBacktest, is_main_board_stock
from config import TABLE_NAME

def load(year, month):
    _, last_day = monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    load_start_dt = start_dt - pd.Timedelta(days=90)
    query = f"SELECT DISTINCT ts_code FROM {TABLE_NAME} ORDER BY ts_code"
    result = execute_with_retry(query, {})
    stock_codes_df = pd.DataFrame(result.fetchall(), columns=result.keys())
    stock_codes = stock_codes_df['ts_code'].tolist()
    stock_data = {}
    batch_size = 50
    for i in range(0, min(len(stock_codes), 200), batch_size):
        batch_codes = stock_codes[i:i + batch_size]
        placeholders = ','.join([f"'{code}'" for code in batch_codes])
        query = f"SELECT ts_code as stock_code, trade_date, open as open_price, close as close_price FROM {TABLE_NAME} WHERE ts_code IN ({placeholders}) AND trade_date >= '{load_start_dt.strftime('%Y-%m-%d')}' AND trade_date <= '{end_dt.strftime('%Y-%m-%d')}' ORDER BY ts_code, trade_date"
        result = execute_with_retry(query, {})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        if df is None or df.empty:
            continue
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        for col in ['open_price', 'close_price']:
            if col in df.columns:
                df[col] = df[col].astype(np.float64)
        for stock_code in df['stock_code'].unique():
            sdf = df[df['stock_code'] == stock_code].copy()
            sdf = sdf.sort_values('trade_date').reset_index(drop=True)
            sdf = calculate_macd(sdf)
            stock_data[stock_code] = sdf
        print(f"B{i//batch_size+1}", end=" ", flush=True)
    print(f"total={len(stock_data)}")
    return stock_data, start_date, end_date

year, month = 2025, 2
print("Loading...")
stock_data, start_date, end_date = load(year, month)
print(f"Stocks loaded: {len(stock_data)}")

in_range = sum(1 for code, df in stock_data.items()
               if len(df[(df['trade_date'] >= pd.to_datetime(start_date)) & (df['trade_date'] <= pd.to_datetime(end_date))]) > 0)
print(f"Stocks with Feb 2025 data: {in_range}")

test_date = pd.Timestamp('2025-02-18')
gc_count = 0
for code, df in stock_data.items():
    if len(df) < 34 or not is_main_board_stock(code):
        continue
    df_r = df.reset_index(drop=True)
    rows = df_r[df_r['trade_date'] == test_date]
    if len(rows) < 1:
        continue
    row_idx = rows.index[0]
    if row_idx == 0:
        continue
    cur = df_r.iloc[row_idx]
    prv = df_r.iloc[row_idx - 1]
    if cur['DIFF'] > 0 and cur['DEA'] > 0 and cur['DIFF'] > cur['DEA'] and prv['DIFF'] <= prv['DEA']:
        gc_count += 1
        if gc_count <= 3:
            print(f"GC: {code} DIFF={cur['DIFF']:.4f} DEA={cur['DEA']:.4f} pDIFF={prv['DIFF']:.4f} pDEA={prv['DEA']:.4f}")

print(f"GC stocks on {test_date.date()}: {gc_count}")
backtest = MonthlyBacktest(initial_capital=10000)
result = backtest.run_monthly_backtest(stock_data, start_date, end_date)
print(f"Trades={result['trade_count']} Final={result['final_capital']:.2f}")
