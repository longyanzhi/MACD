"""
外部全市场选股器 - 基于原始回测逻辑

从PostgreSQL数据库扫描全市场股票，找到满足条件的候选，
通过历史模拟排序，输出最优候选到信号文件，供VNPY策略执行。

输出格式（signal.json）：
{
    "date": "2025-01-15",
    "signal": "buy",           # "buy" | "sell" | "hold" | "none"
    "symbol": "600000.SH",     # 股票代码
    "price": 12.50,            # 参考价格
    "sim_return": 8.5,         # 历史模拟收益率（%）
    "reason": "golden_cross",  # 信号原因
    "timestamp": "..."
}

使用方法（独立运行）：
    python external_stock_selector.py
    python external_stock_selector.py --date 2025-01-15

使用方法（定时任务，每天开盘前运行）：
    配合Windows任务计划程序，或Linux cron：
    0 9 * * 1-5 python /path/to/external_stock_selector.py
"""

import argparse
import json
import sys
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from database import get_stock_data, execute_with_retry, get_all_stock_names
from config import TABLE_NAME, MACD_CONFIG

from macd_indicator import calculate_macd_on_series


# ============================================================
# 配置
# ============================================================

SIGNAL_FILE = Path(__file__).parent / "signal.json"

FAST_PERIOD = MACD_CONFIG.get("fast_period", 12)
SLOW_PERIOD = MACD_CONFIG.get("slow_period", 26)
SIGNAL_PERIOD = MACD_CONFIG.get("signal_period", 9)

LOOKBACK_DAYS = 90
MACD_SMALL_THRESHOLD = 0.05
LIMIT_UP_RATIO = 0.099
BATCH_SIZE = 50


# ============================================================
# 数据加载
# ============================================================

def load_all_stock_codes() -> List[str]:
    """从数据库加载所有股票代码"""
    query = f"SELECT DISTINCT ts_code FROM {TABLE_NAME} ORDER BY ts_code"
    df = get_stock_data(query)
    if df is None or df.empty:
        return []
    return df['ts_code'].tolist()


def load_stock_batch(codes: List[str]) -> pd.DataFrame:
    """批量加载股票数据"""
    if not codes:
        return pd.DataFrame()
    placeholders = ",".join([f"'{code}'" for code in codes])
    query = f"""
        SELECT ts_code as stock_code, trade_date, open, close, high, low, vol
        FROM {TABLE_NAME}
        WHERE ts_code IN ({placeholders})
        ORDER BY ts_code, trade_date
    """
    df = get_stock_data(query)
    if df is None or df.empty:
        return pd.DataFrame()
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    # 统一将价格列转为 float64，防止 Decimal 类型导致运算错误
    for col in ['open', 'close', 'high', 'low', 'vol']:
        if col in df.columns:
            df[col] = df[col].astype(np.float64)
    return df


def load_all_stock_names_map() -> Dict[str, str]:
    """加载股票名称映射"""
    try:
        names = get_all_stock_names()
        if names:
            return names
    except Exception:
        pass
    return {}


# ============================================================
# 历史模拟
# ============================================================

def simulate_trade_on_history(closes: list, macd_arr: list, diff_arr: list, dea_arr: list,
                               window_end: int) -> dict:
    """
    在过去N天窗口内找最近一次金叉买入，MACD下降卖出，计算收益率
    对应 monthly_backtest.py: simulate_trade_on_historical_data
    """
    window_start = max(1, window_end - LOOKBACK_DAYS)

    golden_idx = None
    for i in range(window_end - 1, window_start - 1, -1):
        if i < 1 or i >= len(diff_arr):
            continue
        diff = diff_arr[i]
        dea = dea_arr[i]
        p_diff = diff_arr[i - 1]
        p_dea = dea_arr[i - 1]
        if diff > dea and p_diff <= p_dea and diff > 0 and dea > 0:
            golden_idx = i
            break

    if golden_idx is None:
        return {"return_pct": -999.0, "buy_price": 0.0, "sell_price": 0.0}

    buy_price = closes[golden_idx]

    found_sell = False
    for j in range(golden_idx + 1, len(macd_arr)):
        if j < 1:
            continue
        cur_m = macd_arr[j]
        prev_m = macd_arr[j - 1]
        if cur_m is not None and prev_m is not None and cur_m < prev_m:
            sell_price = closes[j] if j < len(closes) else buy_price
            found_sell = True
            break

    if not found_sell:
        return {"return_pct": -999.0, "buy_price": buy_price, "sell_price": buy_price}

    ret = (sell_price - buy_price) / buy_price * 100
    return {"return_pct": ret, "buy_price": buy_price, "sell_price": sell_price}


# ============================================================
# 过滤检查
# ============================================================

def is_main_board(stock_code: str) -> bool:
    """判断是否为主板股票"""
    code = stock_code.replace(".SZ", "").replace(".SH", "")
    return (
        code.startswith("600") or code.startswith("601") or
        code.startswith("603") or code.startswith("605") or
        code.startswith("000") or code.startswith("001")
    )


def is_limit_up(prev_close: float, prev_prev_close: float) -> bool:
    """判断是否涨停"""
    if prev_prev_close == 0:
        return False
    return (prev_close - prev_prev_close) / prev_prev_close >= LIMIT_UP_RATIO


def is_macd_continuously_small(macd_arr: list, end_idx: int) -> bool:
    """前5日MACD是否持续很小"""
    if end_idx < 5:
        return False
    for i in range(end_idx - 4, end_idx + 1):
        if abs(macd_arr[i]) >= MACD_SMALL_THRESHOLD:
            return False
    return True


# ============================================================
# 核心选股逻辑
# ============================================================

def scan_and_select(target_date: str) -> Optional[dict]:
    """
    全市场扫描 + 历史模拟 + 排序选优
    对应 monthly_backtest.py 的完整选股流程

    Returns:
        最优候选股票信号，或None
    """
    print(f"\n{'='*60}")
    print(f"开始全市场选股扫描 - {target_date}")
    print(f"{'='*60}")

    stock_codes = load_all_stock_codes()
    if not stock_codes:
        print("错误: 无法获取股票列表")
        return None

    print(f"全市场共 {len(stock_codes)} 支股票")

    stock_names = load_all_stock_names_map()

    all_candidates = []
    total_batches = (len(stock_codes) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(stock_codes), BATCH_SIZE):
        batch_codes = stock_codes[batch_idx:batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1

        df = load_stock_batch(batch_codes)
        if df is None or df.empty:
            print(f"  批次 {batch_num}/{total_batches}: 无数据")
            continue

        df['trade_date'] = pd.to_datetime(df['trade_date'])

        for stock_code in df['stock_code'].unique():
            stock_df = df[df['stock_code'] == stock_code].copy()
            stock_df = stock_df.sort_values('trade_date').reset_index(drop=True)

            candidate = check_single_stock(stock_df, stock_code, target_date, stock_names)
            if candidate:
                all_candidates.append(candidate)

        print(f"\r扫描进度: {batch_num}/{total_batches} ({batch_num * 100 // total_batches}%)", end='', flush=True)

    print(f"\n共发现 {len(all_candidates)} 只候选股票")

    if not all_candidates:
        print("无候选股票")
        return None

    # 按历史模拟收益率排序
    all_candidates.sort(key=lambda x: x['sim_return'], reverse=True)

    # 显示候选列表
    print(f"\n候选股票（按历史模拟收益率排序，前10）:")
    print(f"{'代码':<14} {'名称':<10} {'模拟收益率':<12} {'前MACD<0':<10} {'非涨停':<8} {'非ST':<6} {'非持续小':<8}")
    print("-" * 80)
    for c in all_candidates[:10]:
        print(f"{c['symbol']:<14} {c['name']:<10} {c['sim_return']:<12.2f}% "
              f"{str(c['prev_macd_neg']):<10} {str(c['not_limit_up']):<8} "
              f"{str(c['not_st']):<6} {str(c['macd_not_small']):<8}")

    # 逐个检查过滤条件
    for candidate in all_candidates:
        if candidate['prev_macd_neg'] and candidate['not_limit_up'] \
                and candidate['not_st'] and candidate['macd_not_small']:
            print(f"\n最优候选: {candidate['symbol']} {candidate['name']}")
            print(f"  历史模拟收益率: {candidate['sim_return']:.2f}%")
            return candidate

    print("\n所有候选均未通过过滤条件")
    return None


def check_single_stock(df: pd.DataFrame, stock_code: str, target_date: str,
                       stock_names: Dict[str, str]) -> Optional[dict]:
    """检查单支股票"""
    if len(df) < 40:
        return None

    # 先主板过滤（与回测逻辑一致）
    if not is_main_board(stock_code):
        return None

    target_dt = pd.to_datetime(target_date)

    # 找到目标日期
    target_rows = df[df['trade_date'] == target_dt]
    if len(target_rows) == 0:
        return None
    target_idx = target_rows.index[0]
    orig_target_idx = list(df.index).index(target_idx)

    # 往前取足够的数据计算MACD
    start_idx = max(0, orig_target_idx - 60)
    slice_df = df.iloc[start_idx:orig_target_idx + 1].copy()
    if len(slice_df) < 40:
        return None

    closes = slice_df['close'].tolist()
    diff_arr, dea_arr, macd_arr = calculate_macd_on_series(closes)

    cur_idx = len(slice_df) - 1
    prev_idx = cur_idx - 1

    if prev_idx < 0:
        return None

    diff = diff_arr[cur_idx]
    dea = dea_arr[cur_idx]
    prev_diff = diff_arr[prev_idx]
    prev_dea = dea_arr[prev_idx]
    prev_macd = macd_arr[prev_idx]

    # 金叉条件
    if not (diff > dea and prev_diff <= prev_dea and diff > 0 and dea > 0):
        return None

    # 历史模拟
    sim_result = simulate_trade_on_history(closes, macd_arr, diff_arr, dea_arr, cur_idx)

    # 过滤条件
    prev_macd_neg = prev_macd < 0

    # 涨停检查（前一根K线）
    limit_up = False
    if orig_target_idx >= 2:
        prev_close = df.iloc[orig_target_idx - 1]['close']
        prev_prev_close = df.iloc[orig_target_idx - 2]['close']
        limit_up = is_limit_up(prev_close, prev_prev_close)

    # ST检查
    name = stock_names.get(stock_code, "")
    not_st = "ST" not in name.upper()

    # MACD持续很小检查
    macd_not_small = not is_macd_continuously_small(macd_arr, prev_idx)

    return {
        "symbol": stock_code,
        "name": name,
        "golden_date": target_date,
        "golden_price": closes[-1],
        "sim_return": sim_result['return_pct'],
        "sim_buy_price": sim_result['buy_price'],
        "sim_sell_price": sim_result['sell_price'],
        "prev_macd_neg": prev_macd_neg,
        "not_limit_up": not limit_up,
        "not_st": not_st,
        "macd_not_small": macd_not_small,
    }


# ============================================================
# 信号输出
# ============================================================

def write_signal(signal_data: dict):
    """写入信号文件（JSON格式）"""
    signal_data['timestamp'] = datetime.now().isoformat()
    with open(SIGNAL_FILE, 'w', encoding='utf-8') as f:
        json.dump(signal_data, f, ensure_ascii=False, indent=2)
    print(f"信号已写入: {SIGNAL_FILE}")
    print(json.dumps(signal_data, ensure_ascii=False, indent=2))


def read_signal() -> Optional[dict]:
    """读取当前信号文件"""
    if not SIGNAL_FILE.exists():
        return None
    try:
        with open(SIGNAL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def clear_signal():
    """清除信号文件"""
    if SIGNAL_FILE.exists():
        SIGNAL_FILE.unlink()


# ============================================================
# 主入口
# ============================================================

def run(target_date: str = None):
    """
    执行全市场选股扫描

    Args:
        target_date: 目标日期，格式 'YYYY-MM-DD'，默认为今天
    """
    if target_date is None:
        target_date = date.today().strftime("%Y-%m-%d")

    print(f"MACD外部选股器")
    print(f"目标日期: {target_date}")
    print(f"信号文件: {SIGNAL_FILE}")

    try:
        candidate = scan_and_select(target_date)

        if candidate:
            signal_data = {
                "date": target_date,
                "signal": "buy",
                "symbol": candidate['symbol'],
                "name": candidate['name'],
                "price": float(candidate['golden_price']),
                "sim_return": float(candidate['sim_return']),
                "reason": "golden_cross_with_history_sim",
            }
            write_signal(signal_data)
        else:
            signal_data = {
                "date": target_date,
                "signal": "none",
                "symbol": "",
                "price": 0.0,
                "sim_return": 0.0,
                "reason": "no_candidates",
            }
            write_signal(signal_data)

        return signal_data

    except Exception as e:
        print(f"\n选股过程出错: {e}")
        import traceback
        traceback.print_exc()

        signal_data = {
            "date": target_date,
            "signal": "error",
            "symbol": "",
            "price": 0.0,
            "sim_return": 0.0,
            "reason": str(e),
        }
        write_signal(signal_data)
        return signal_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MACD外部全市场选股器")
    parser.add_argument("--date", type=str, default=None,
                        help="目标日期，格式 YYYY-MM-DD，默认为今天")
    parser.add_argument("--clear", action="store_true",
                        help="清除信号文件后退出")
    args = parser.parse_args()

    if args.clear:
        clear_signal()
        print("信号文件已清除")
    else:
        if args.date is None:
            default = date.today().strftime("%Y-%m-%d")
            user_input = input(f"请输入目标日期（直接回车使用今天 {default}）: ").strip()
            args.date = user_input if user_input else default
        run(args.date)
