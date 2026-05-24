"""
MACD 实时选股信号器
用于盘中实时检测金叉信号，输出到 signals.txt 供 AutoHotkey 使用

使用方式:
    python realtime_scanner.py                    # 扫描当天信号
    python realtime_scanner.py --date 2026-04-29  # 扫描指定日期信号
    python realtime_scanner.py --watch             # 每5分钟持续监控（盘中）

输出文件: signals.txt
格式: 股票代码,股票名称,金叉时间,预期收益率
"""

import sys
import os
import time
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, date
from database import get_stock_data, check_table_exists, get_stock_count, execute_with_retry, load_all_stock_data, get_all_stock_names
from macd_calculator import calculate_macd, find_golden_cross

SIGNAL_FILE = os.path.join(os.path.dirname(__file__), "buy_signal.txt")
LOG_FILE = os.path.join(os.path.dirname(__file__), "scanner_log.txt")

# 股票名称缓存
_stock_names_cache = None


def _get_stock_names() -> dict:
    """获取股票名称缓存"""
    global _stock_names_cache
    if _stock_names_cache is None:
        _stock_names_cache = get_all_stock_names()
    return _stock_names_cache


def is_st_stock(stock_code: str) -> bool:
    """检查是否为ST股"""
    names = _get_stock_names()
    name = names.get(stock_code, '')
    return 'ST' in name.upper()


def simulate_trade_on_historical_data(df: pd.DataFrame, current_date: pd.Timestamp):
    """
    在历史数据上模拟交易以计算收益率（用于选股阶段）。
    回看90天窗口，以最近一次金叉作为买入点，MACD下降作为卖出点。
    注意：df 需要包含足够的预热数据（窗口开始前60天）用于正确计算 MACD
    """
    df = df.reset_index(drop=True)
    window_end = current_date - pd.Timedelta(days=1)
    window_start = window_end - pd.Timedelta(days=90)

    mask = (df['trade_date'] >= window_start) & (df['trade_date'] <= window_end)
    trade_range = df[mask].copy()

    if len(trade_range) < 2:
        return None

    # 找最近一次金叉（模拟历史交易，只需 DIFF>0，DEA 不强制要求在零轴以上）
    golden_cross_idx = None
    for i in range(len(trade_range) - 1, 0, -1):
        current = trade_range.iloc[i]
        prev = trade_range.iloc[i - 1]

        if (current['DIFF'] > 0 and
            current['DIFF'] > current['DEA'] and
            prev['DIFF'] <= prev['DEA']):
            golden_cross_idx = i
            break

    if golden_cross_idx is None:
        return None

    buy_price = float(trade_range.iloc[golden_cross_idx]['close_price'])

    # 找第一个MACD下降点作为卖出
    for j in range(golden_cross_idx + 1, len(trade_range)):
        current = trade_range.iloc[j]
        prev = trade_range.iloc[j - 1]

        if pd.notna(current['MACD']) and pd.notna(prev['MACD']):
            if current['MACD'] < prev['MACD']:
                sell_price = float(current['close_price'])
                return_rate = (sell_price - buy_price) / buy_price * 100
                return return_rate

    return None  # 金叉后没有卖出信号（窗口内持续上涨）


def log(msg):
    """写入日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def is_main_board_stock(stock_code: str) -> bool:
    """判断是否为主板股票（排除创业板688、风险警示板ST）"""
    if stock_code.startswith("688") or stock_code.endswith(".BJ"):
        return False
    return True


def scan_today_signals(target_date=None) -> list:
    """
    扫描指定日期的金叉信号

    Args:
        target_date: 日期字符串或datetime，默认今天

    Returns:
        信号列表，每项为 dict
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")
    elif isinstance(target_date, datetime):
        target_date = target_date.strftime("%Y-%m-%d")
    else:
        target_date = target_date.split()[0]

    target_dt = pd.to_datetime(target_date)
    
    # 计算窗口和 MACD 预热需要的日期
    window_end = target_dt - pd.Timedelta(days=1)
    window_start = window_end - pd.Timedelta(days=90)
    # 需要额外加载 60 天历史数据用于 MACD 计算（talib 需要较长的预热期）
    macd_warmup_start = window_start - pd.Timedelta(days=60)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在加载数据 {macd_warmup_start.strftime('%Y-%m-%d')} ~ {target_date} ...")
    stock_data = load_all_stock_data(macd_warmup_start.strftime("%Y-%m-%d"), target_date)

    if not stock_data:
        print("未加载到任何股票数据，请检查数据库或日期是否有效")
        return []

    target_dt = pd.to_datetime(target_date)
    signals = []

    for stock_code, df in stock_data.items():
        if len(df) < 34:
            continue
        if not is_main_board_stock(stock_code):
            continue

        df = df.reset_index(drop=True)

        # 计算 MACD 指标
        df = calculate_macd(df, price_column='close_price')

        # 检查目标日期是否有金叉
        rows = df[df['trade_date'] == target_dt]
        if len(rows) < 1:
            continue

        row_idx = rows.index[0]
        if row_idx == 0:
            continue

        current = df.iloc[row_idx]
        prev = df.iloc[row_idx - 1]

        # 选股条件：DIFF>0, DEA>0, 金叉
        diff_curr = current.get('DIFF', 0) or 0
        dea_curr = current.get('DEA', 0) or 0
        diff_prev = prev.get('DIFF', 0) or 0
        dea_prev = prev.get('DEA', 0) or 0

        is_golden = (diff_curr > 0 and dea_curr > 0 and diff_curr > dea_curr and diff_prev <= dea_prev)

        if not is_golden:
            continue

        # 过滤：前一日MACD<0
        if row_idx < 2:
            continue
        prev2 = df.iloc[row_idx - 1]
        macd_prev = prev2.get('MACD', 0) or 0
        if macd_prev >= 0:
            continue

        # 过滤：前5日MACD不为持续很小
        too_small = True
        for k in range(2, min(7, row_idx + 1)):
            macd_k = df.iloc[row_idx - k].get('MACD', 0) or 0
            if macd_k > -0.5:
                too_small = False
                break
        if too_small:
            continue

        # 过滤：涨停（非严格，需当日收盘数据）
        if row_idx >= 1:
            prev_close = df.iloc[row_idx - 1].get('close_price', 0) or 0
            curr_close = current.get('close_price', 0) or 0
            if prev_close > 0 and (curr_close / prev_close - 1) >= 0.095:
                continue

        # 过滤：ST股
        if is_st_stock(stock_code):
            continue

        # 获取模拟收益率（回看90天窗口，找最近一次金叉模拟交易）
        sim_return = simulate_trade_on_historical_data(df, target_dt)

        signals.append({
            'stock_code': stock_code,
            'date': target_date,
            'diff': diff_curr,
            'dea': dea_curr,
            'macd': current.get('MACD', 0) or 0,
            'close_price': current.get('close_price', 0) or 0,
            'sim_return': sim_return,
        })

    # 按模拟收益率排序
    signals.sort(key=lambda x: x['sim_return'] if x['sim_return'] is not None else -999, reverse=True)
    return signals


def save_signals(signals: list):
    """保存信号到文件"""
    with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
        # 写入原始格式供AHK解析
        f.write("\n# RAW_DATA\n")
        for i, sig in enumerate(signals, 1):
            ret = sig['sim_return'] if sig['sim_return'] is not None else -999
            f.write(f"{i}|{sig['stock_code']}|{sig['close_price']:.2f}|{sig['diff']:.4f}|{sig['dea']:.4f}|{sig['macd']:.4f}|{ret:.2f}\n")


def get_last_trading_day(target_date=None):
    """获取最后一个交易日（跳过周末）"""
    if target_date is None:
        target_date = date.today()
    elif isinstance(target_date, str):
        target_date = pd.to_datetime(target_date).date()

    # 回溯到前一天
    target_date = target_date - timedelta(days=1)

    # 如果是周末，继续回溯到周五
    while target_date.weekday() >= 5:  # 5=周六, 6=周日
        target_date = target_date - timedelta(days=1)

    return target_date.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="MACD 实时选股信号器")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="指定扫描日期，格式 YYYY-MM-DD，默认为当天"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="持续监控模式，每5分钟扫描一次（仅在交易时段有效）"
    )
    args = parser.parse_args()

    if args.date:
        try:
            pd.to_datetime(args.date)
        except Exception:
            print(f"日期格式错误: {args.date}，应为 YYYY-MM-DD")
            return
        target_date = args.date
    else:
        target_date = get_last_trading_day()

    log(f"=== MACD 实时选股启动 === 日期: {target_date} ===")

    if not check_table_exists():
        log("数据库连接失败！")
        return

    stock_count = get_stock_count()
    log(f"数据库共 {stock_count} 支股票")

    def run_scan():
        log(f"开始扫描日期: {target_date}")
        signals = scan_today_signals(target_date)
        save_signals(signals)
        log(f"扫描完成，发现 {len(signals)} 信号股")

        if signals:
            best = signals[0]
            log(f"最优信号: {best['stock_code']} @ {best['close_price']:.2f}")

            # 打印 top 信号
            top3 = signals[:3]
            for s in top3:
                ret_str = f"{s['sim_return']:.2f}%" if s['sim_return'] else "N/A"
                log(f"  → {s['stock_code']} | 收盘 {s['close_price']:.2f} | 预期收益 {ret_str}")

    run_scan()

    if args.watch:
        log("进入持续监控模式，按 Ctrl+C 停止...")
        while True:
            time.sleep(300)  # 5分钟
            run_scan()


if __name__ == "__main__":
    main()
