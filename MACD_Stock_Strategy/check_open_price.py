"""
开盘价偏离检查脚本

功能：
  - 在 9:30 开盘价确定后运行
  - 从 buy_signal.txt 读取信号股（代码 + 参考价）
  - 调用 tushare 实时接口获取今日开盘价
  - 计算偏离百分比，判断是否超过 3% 阈值
  - 结果追加写入 buy_signal.txt

使用方式:
  python check_open_price.py   # 检查买入信号股
"""

import sys
import os
import time
import argparse
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))

from config import TUSHARE_CONFIG


import tushare as ts
import tushare.pro.client as client
client.DataApi._DataApi__http_url = "http://tushare.xyz"
pro = ts.pro_api(TUSHARE_CONFIG['token'])

# ===== 配置 =====
BUY_SIGNAL_FILE = os.path.join(os.path.dirname(__file__), "buy_signal.txt")
LOG_FILE = os.path.join(os.path.dirname(__file__), "open_price_log.txt")
SIGNAL_FILE = os.path.join(os.path.dirname(__file__), "signalS.txt")
OPEN_PRICE_DEVIATION_THRESHOLD = 3.0
MAX_RETRIES = 5


def log(msg: str):
    """同时打印和写入日志"""
    from datetime import datetime
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
    """
    带重试的通用调用。
    func 返回以下两种格式均可：
      - 单值：result / None  （retry_call 包装为 (result, None)）
      - 元组：(result, error)  （直接透传）
    """
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = func(*args, **kwargs)

            # 如果函数已返回 (value, error) 格式，直接透传
            if isinstance(result, tuple) and len(result) == 2:
                value, err = result
                if value is not None:
                    return result
                last_error = err or "返回 None"
            elif result is not None:
                return result, None
            else:
                last_error = "返回 None"
        except Exception as e:
            last_error = str(e)

        wait = 5 if "频率" not in (last_error or "") else 15
        log(f"  [重试] 第{attempt + 1}次失败，{wait}秒后重试: {last_error}")
        time.sleep(wait)

    return None, last_error


def get_open_price_tushare(stock_code: str) -> tuple:
    """
    用 tushare rt_k 实时日线接口获取今日开盘价。
    返回 (open_price: float | None, error: str | None)
    """
    try:
        df = pro.rt_k(ts_code=stock_code)
        if df is not None and len(df) > 0:
            open_price = float(df.iloc[0]['open'])
            return open_price, None
    except Exception as e:
        return None, f"tushare rt_k: {e}"

    return None, "无法获取开盘价"


def check(stock_code: str, reference_price: float) -> dict:
    """
    检查开盘价偏离

    Returns:
        dict: {
            'stock_code': str,
            'reference_price': float,
            'open_price': float,
            'deviation': float,    # 偏离百分比
            'can_buy': bool,
            'reason': str
        }
    """
    log(f"")
    log(f"{'=' * 55}")
    log(f"  开盘价偏离检查  {date.today()}")
    log(f"  股票: {stock_code}")
    log(f"  参考价: {reference_price:.2f}")
    log(f"{'=' * 55}")

    log("[Step 1] 获取今日开盘价...")
    open_price, err = retry_call(get_open_price_tushare, stock_code)
    if open_price is None or open_price <= 0:
        log(f"  [错误] 无法获取今日开盘价: {err}")
        return {
            'stock_code': stock_code,
            'reference_price': reference_price,
            'open_price': None,
            'deviation': 0.0,
            'can_buy': True,   # 获取不到时默认允许
            'reason': f"无法获取开盘价（{err}），跳过检查"
        }

    log("[Step 2] 计算偏离...")
    deviation = (open_price - reference_price) / reference_price * 100

    log(f"  参考价: {reference_price:.2f}")
    log(f"  开盘价: {open_price:.2f}")
    log(f"  偏离:   {deviation:+.2f}%")

    can_buy = abs(deviation) <= OPEN_PRICE_DEVIATION_THRESHOLD
    if can_buy:
        reason = "正常"
        log(f"  通过：偏离 {deviation:+.2f}% 在 {OPEN_PRICE_DEVIATION_THRESHOLD}% 阈值内")
    else:
        reason = f"开盘价偏离 {deviation:+.2f}% > {OPEN_PRICE_DEVIATION_THRESHOLD}%，放弃信号"
        log(f"  *** 放弃：{reason} ***")

    return {
        'stock_code': stock_code,
        'reference_price': reference_price,
        'open_price': open_price,
        'deviation': deviation,
        'can_buy': can_buy,
        'reason': reason
    }


def _read_file(path: str, encodings=("utf-8", "gbk", "gb2312")) -> list:
    """尝试多种编码读取文件"""
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.readlines()
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("utf-8", b"", 0, 1, "无法用任何编码读取文件")


def read_buy_signal() -> tuple:
    """
    从 buy_signal.txt 读取信号股代码和参考价。
    支持两种格式：
      1. RAW_DATA 格式（realtime_scanner.py 写入）: 1|301630.SZ|240.40|...
      2. 参考价格式（macd_test_mode.ahk 写入）: 参考价: 240.40
    Returns: (stock_code: str, reference_price: float)
    """
    if not os.path.exists(BUY_SIGNAL_FILE):
        log(f"[错误] 找不到买入信号文件: {BUY_SIGNAL_FILE}")
        log("请先运行选股（F6 / Ctrl+Alt+S）")
        return None, None

    stock_code = None
    reference_price = None

    for line in _read_file(BUY_SIGNAL_FILE):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        # RAW_DATA 格式: 1|stock_code|price|diff|dea|macd|ret
        if len(fields) >= 3 and fields[0].isdigit() and stock_code is None:
            stock_code = fields[1]
            try:
                reference_price = float(fields[2])
            except (ValueError, IndexError):
                pass

    return stock_code, reference_price


def append_result_to_signal(result: dict):
    """将检查结果追加写入 signals.txt"""
    for enc in ("utf-8", "gbk"):
        try:
            with open(SIGNAL_FILE, "a", encoding=enc) as f:
                f.write(f"\n开盘价: {result['open_price']:.2f}\n")
                f.write(f"开盘偏离: {result['deviation']:+.2f}%\n")
                if result['open_price'] is None:
                    f.write(f"状态: 警告-无法获取开盘价\n")
                elif result['can_buy']:
                    f.write(f"状态: 通过\n")
                else:
                    f.write(f"状态: 放弃\n")
            return
        except UnicodeEncodeError:
            continue
    log(f"[错误] 写入信号文件失败")


# ============================================================================
# 主入口
# ============================================================================

def main():
    stock_code, reference_price = read_buy_signal()
    if not stock_code:
        sys.exit(1)
    if not reference_price:
        log("[错误] 未能从信号文件中解析出参考价")
        sys.exit(1)

    result = check(stock_code, reference_price)
    append_result_to_signal(result)

    log(f"")
    log(f"{'=' * 55}")
    if result['open_price'] is None:
        log(f"  结果: 警告 - 无法获取开盘价")
    elif result['can_buy']:
        log(f"  结果: 通过（偏离 {result['deviation']:+.2f}%）")
    else:
        log(f"  结果: 放弃（偏离 {result['deviation']:+.2f}%）")
    log(f"{'=' * 55}")


if __name__ == "__main__":
    main()
