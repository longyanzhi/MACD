"""
MACD 收盘前监控脚本

功能：
  - 在收盘前5分钟（14:55）运行
  - 从数据库获取历史60天数据
  - 从 tushare 获取当日实时价格
  - 用实时价格替换今日收盘价，计算当前 MACD
  - 与昨日 MACD 对比：MACD 由正转负 + DIFF 下降 => 卖出
  - 止损逻辑：亏损超过阈值强制卖出

使用方式:
  python realtime_macd_monitor.py              # 单次检查
  python realtime_macd_monitor.py --watch     # 持续监控到14:55
  python realtime_macd_monitor.py --stock 000601.SZ  # 指定股票
"""

import sys
import os
import time
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from config import MACD_CONFIG, TUSHARE_CONFIG
from macd_calculator import (
    calculate_macd_talib,
    calculate_macd_manual,
    TALIB_AVAILABLE,
)
from database import get_stock_data

# ===== Tushare 初始化 =====
try:
    import tushare as ts
except ImportError:
    print("错误：未安装 tushare，请运行: pip install tushare")
    sys.exit(1)

import tushare.pro.client as client
client.DataApi._DataApi__http_url = "http://tushare.xyz"
pro = ts.pro_api(TUSHARE_CONFIG['token'])

# ===== 参数配置 =====
FAST = MACD_CONFIG['fast_period']      # 12
SLOW = MACD_CONFIG['slow_period']      # 26
SIGNAL = MACD_CONFIG['signal_period']  # 9
HISTORY_DAYS = 60                      # 从数据库获取的历史天数
STOP_LOSS_THRESHOLD = -7.0             # 止损阈值（亏损%）
LOG_FILE = os.path.join(os.path.dirname(__file__), "macd_monitor_log.txt")

# tushare 重试配置
MAX_RETRIES = 5
RETRY_DELAY = 5


def log(msg: str):
    """同时打印和写入日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    for enc in ("utf-8", "gbk"):
        try:
            with open(LOG_FILE, "a", encoding=enc) as f:
                f.write(line + "\n")
            return
        except UnicodeEncodeError:
            continue


def retry_call(func, *args, **kwargs):
    """带重试的通用调用"""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = func(*args, **kwargs)
            if result is not None:
                return result, None
            last_error = "返回 None"
        except Exception as e:
            last_error = str(e)
            if "频率" in last_error:
                wait = 15
            else:
                wait = RETRY_DELAY
            log(f"  [重试] 第{attempt+1}次失败，{wait}秒后重试: {last_error}")
            time.sleep(wait)
    return None, last_error


def get_realtime_price(stock_code: str) -> float:
    """从 tushare 获取当日实时价格（后复权）"""
    log(f"  [数据] 从 tushare 获取实时价格...")
    result, err = retry_call(pro.rt_k, ts_code=stock_code)
    if result is not None and len(result) > 0:
        price = float(result.iloc[-1]['close'])
        log(f"  [数据] 实时价格: {price:.2f}")
        return price
    log(f"  [错误] 实时价格获取失败: {err}")
    return None


def load_historical_data(stock_code: str) -> pd.DataFrame:
    """
    从数据库加载历史数据（不含今日）
    返回按日期排序的 DataFrame，包含 stock_code, trade_date, open_price, close_price, high_price, low_price, volume
    """
    start_date = (date.today() - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    end_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    log(f"  [数据] 从数据库加载历史数据: {start_date} ~ {end_date}")
    df = get_stock_data(stock_code, start_date=start_date, end_date=end_date)

    if df is None or df.empty:
        log("  [错误] 数据库无历史数据")
        return pd.DataFrame()

    df = df.sort_values('trade_date').reset_index(drop=True)
    log(f"  [数据] 历史数据 {len(df)} 条")
    return df

def calculate_macd_from_df(df: pd.DataFrame) -> dict:
    """
    用 DataFrame 中的价格数据计算 MACD
    df 需要包含 close_price 列
    返回最后一行的 DIFF, DEA, MACD, close
    """
    if len(df) < SLOW:
        return None

    closes = df['close_price'].astype(np.float64).values

    diff, dea, macd = calculate_macd_talib(closes, FAST, SLOW, SIGNAL)

    return {
        'diff': float(diff[-1]),
        'dea': float(dea[-1]),
        'macd': float(macd[-1]),
        'close': float(closes[-1]),
    }


def calculate_profit_pct(buy_price: float, current_price: float) -> float:
    if buy_price <= 0:
        return 0.0
    return (current_price - buy_price) / buy_price * 100


def judge(macd_prev: dict, macd_now: dict, buy_price: float) -> tuple:
    """
    核心判断逻辑

    Returns:
        (action: str, details: dict)
        action: 'SELL' | 'STOP_LOSS' | 'HOLD' | 'ERROR'
    """
    current_price = macd_now['close']
    profit_pct = calculate_profit_pct(buy_price, current_price)

    details = {
        'current': macd_now,
        'previous': macd_prev,
        'buy_price': buy_price,
        'profit_pct': profit_pct,
    }

    log(f"")
    log(f"  === 判断 ===")
    log(f"  当前价格: {current_price:.2f}  |  持仓成本: {buy_price:.2f}  |  盈亏: {profit_pct:+.2f}%")
    log(f"  昨日 MACD: DIFF={macd_prev['diff']:.4f}  DEA={macd_prev['dea']:.4f}  MACD={macd_prev['macd']:.4f}")
    log(f"  当前 MACD: DIFF={macd_now['diff']:.4f}  DEA={macd_now['dea']:.4f}  MACD={macd_now['macd']:.4f}")

    # 1. 止损判断
    if profit_pct <= STOP_LOSS_THRESHOLD:
        log(f"  *** 触发止损: 亏损 {profit_pct:.2f}% > {STOP_LOSS_THRESHOLD}% ***")
        return 'STOP_LOSS', details

    # 2. MACD 卖出判断：MACD 下降
    macd_turned_down = (macd_now['macd'] < macd_prev['macd'])

    log(f"  MACD减小: {macd_turned_down}")

    if macd_turned_down:
        log(f"  *** 触发卖出信号 ***")
        return 'SELL', details

    log(f"  继续持有")
    return 'HOLD', details



def check(stock_code: str, buy_price:float) -> tuple:
    """
    执行一次完整的 MACD 监控检查

    流程：
      1. 从数据库加载历史数据（不含今日）
      2. 用历史数据计算"昨日 MACD"
      3. 获取 tushare 实时价格，追加/替换今日行，计算"当前 MACD"
      4. 对比判断是否卖出
    """
    log(f"")
    log(f"{'='*55}")
    log(f"  MACD 收盘前监控  {datetime.now().strftime('%H:%M:%S')}")
    log(f"  股票: {stock_code}")
    log(f"{'='*55}")

    # Step 1: 加载历史数据
    log("[Step 1] 加载历史数据...")
    df_hist = load_historical_data(stock_code)
    if df_hist.empty or len(df_hist) < SLOW:
        log("  [错误] 历史数据不足，无法计算 MACD（需要至少 26 条）")
        return 'ERROR', None

    # Step 2: 计算"昨日 MACD"（用不含今日的历史数据）
    log("[Step 2] 计算昨日 MACD...")
    macd_prev = calculate_macd_from_df(df_hist)
    if macd_prev is None:
        log("  [错误] MACD 计算失败")
        return 'ERROR', None
    log(f"  昨日 MACD: DIFF={macd_prev['diff']:.4f}  DEA={macd_prev['dea']:.4f}  MACD={macd_prev['macd']:.4f}")
    log(f"  昨日收盘价: {macd_prev['close']:.2f}")

    # Step 3: 获取实时价格，构建今日数据，计算"当前 MACD"
    log("[Step 3] 获取实时价格并计算当前 MACD...")
    realtime_price = get_realtime_price(stock_code)
    if realtime_price is None or realtime_price <= 0:
        log("  [错误] 无法获取实时价格")
        return 'ERROR', None

    today_str = date.today().strftime("%Y-%m-%d")
    today_dt = pd.to_datetime(today_str)

    # 检查今日是否已有数据：有则替换，无则追加
    today_rows = df_hist[df_hist['trade_date'].dt.strftime("%Y-%m-%d") == today_str]

    if today_rows.empty:
        new_row = pd.DataFrame([{
            'stock_code': stock_code,
            'trade_date': today_dt,
            'open_price': realtime_price,
            'close_price': realtime_price,
            'high_price': realtime_price,
            'low_price': realtime_price,
            'volume': 0.0,
        }])
        df_today = pd.concat([df_hist, new_row], ignore_index=True)
    else:
        df_today = df_hist.copy()
        idx = today_rows.index[0]
        df_today.loc[idx, 'close_price'] = realtime_price
        df_today.loc[idx, 'high_price'] = max(df_today.loc[idx, 'high_price'], realtime_price)
        df_today.loc[idx, 'low_price'] = min(df_today.loc[idx, 'low_price'], realtime_price)

    macd_now = calculate_macd_from_df(df_today)
    if macd_now is None:
        log("  [错误] 当前 MACD 计算失败")
        return 'ERROR', None
    log(f"  当前 MACD: DIFF={macd_now['diff']:.4f}  DEA={macd_now['dea']:.4f}  MACD={macd_now['macd']:.4f}")
    log(f"  实时价格: {macd_now['close']:.2f}")

    # Step 4: 判断
    log("[Step 4] 判断...")

    return judge(macd_prev, macd_now, buy_price)


def main():
    global STOP_LOSS_THRESHOLD

    parser = argparse.ArgumentParser(description="MACD 收盘前监控")
    parser.add_argument("--stock", type=str, help="指定股票代码）")
    parser.add_argument("--buy-price", type=float, default=None, help="买入价格")
    args = parser.parse_args()

    target_stock = args.stock
    buy_price = args.buy_price

    log(f"")
    log(f"{'='*55}")
    log(f"  MACD 收盘前监控")
    log(f"  股票: {target_stock}")
    log(f"  买入价: {buy_price:.2f}")
    log(f"  止损阈值: {STOP_LOSS_THRESHOLD}%")
    log(f"{'='*55}")

    action, details = check(target_stock, buy_price)

    # 输出结果
    log(f"")
    log(f"{'='*55}")
    log(f"  检查结果: {action}")
    if details:
        log(f"  盈亏: {details['profit_pct']:+.2f}%")
    log(f"{'='*55}")

    # 写入信号文件
    if action in ('SELL', 'STOP_LOSS'):
        signal_file = os.path.join(os.path.dirname(__file__), "sell_signal.txt")
        reason = "MACD下降" if action == 'SELL' else f"止损({details['profit_pct']:.2f}%)"

        with open(signal_file, "w", encoding="utf-8") as f:
            f.write(f"{target_stock}|SELL|{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"价格: {details['current']['close']:.2f}\n")
            f.write(f"原因: {reason}\n")
            f.write(f"盈亏: {details['profit_pct']:+.2f}%\n")
            f.write(f"MACD: {details['current']['macd']:.4f}\n")

        log(f"")
        log(f"*** {'卖出' if action == 'SELL' else '止损'}信号已写入 sell_signal.txt ***")


if __name__ == "__main__":
    main()
