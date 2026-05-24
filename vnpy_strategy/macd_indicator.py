"""
MACD技术指标计算模块
用于在VNPY策略中对历史K线数据进行MACD预计算

MACD(12,26,9) 计算逻辑：
- DIFF = EMA(close, 12) - EMA(close, 26)
- DEA = EMA(DIFF, 9)
- MACD柱 = (DIFF - DEA) * 2
"""

import pandas as pd
import numpy as np


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    return prices.ewm(span=period, adjust=False).mean()


def calculate_macd_on_series(close_prices,
                             fast_period: int = 12,
                             slow_period: int = 26,
                             signal_period: int = 9):
    """
    计算MACD指标

    Args:
        close_prices: pd.Series 或普通列表/数组

    Returns:
        diff, dea, macd_histogram (all pd.Series)
    """
    if not isinstance(close_prices, pd.Series):
        close_prices = pd.Series(close_prices)

    close_prices = close_prices.astype(np.float64)

    ema_fast = calculate_ema(close_prices, fast_period)
    ema_slow = calculate_ema(close_prices, slow_period)
    diff = ema_fast - ema_slow
    dea = calculate_ema(diff, signal_period)
    macd_histogram = (diff - dea) * 2
    return diff, dea, macd_histogram


def is_golden_cross(diff: float, dea: float,
                    prev_diff: float, prev_dea: float) -> bool:
    """金叉：DIFF上穿DEA"""
    return (diff > dea) and (prev_diff <= prev_dea)


def is_dead_cross(diff: float, dea: float,
                  prev_diff: float, prev_dea: float) -> bool:
    """死叉：DIFF下穿DEA"""
    return (diff < dea) and (prev_diff >= prev_dea)


def check_golden_cross_conditions(diff: float, dea: float,
                                  prev_diff: float, prev_dea: float,
                                  require_diff_above_zero: bool = True,
                                  require_dea_above_zero: bool = True) -> bool:
    """
    检查是否满足MACD金叉买入的全部条件

    条件：
    1. DIFF > 0
    2. DEA > 0
    3. DIFF上穿DEA（金叉）
    """
    cond1 = (not require_diff_above_zero) or (diff > 0)
    cond2 = (not require_dea_above_zero) or (dea > 0)
    cond3 = is_golden_cross(diff, dea, prev_diff, prev_dea)
    return cond1 and cond2 and cond3


def compute_macd_features(bar_data_list: list) -> pd.DataFrame:
    """
    将VNPY的BarData列表转换为DataFrame并计算MACD指标

    Args:
        bar_data_list: VNPY BarData对象列表（按时间排序）

    Returns:
        包含OHLCV和MACD指标的DataFrame
    """
    records = []
    for bar in bar_data_list:
        records.append({
            'datetime': bar.datetime,
            'open_price': bar.open_price,
            'high_price': bar.high_price,
            'low_price': bar.low_price,
            'close_price': bar.close_price,
            'volume': bar.volume,
        })

    df = pd.DataFrame(records)
    diff, dea, macd_histogram = calculate_macd_on_series(df['close_price'])
    df['diff'] = diff.values
    df['dea'] = dea.values
    df['macd'] = macd_histogram.values
    return df
