"""
MACD指标计算模块
支持talib库（如果可用）和手动计算两种方式
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, List
from config import MACD_CONFIG


def try_import_talib():
    """尝试导入talib"""
    try:
        import talib
        return True
    except ImportError:
        return False


TALIB_AVAILABLE = try_import_talib()


def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
    """
    计算指数移动平均线 (EMA)
    """
    return prices.astype(np.float64).ewm(span=period, adjust=False).mean()


def calculate_macd_manual(close_prices: pd.Series,
                          fast_period: int = 12, 
                          slow_period: int = 26, 
                          signal_period: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    手动计算MACD指标
    """
    ema_fast = calculate_ema(close_prices, fast_period)
    ema_slow = calculate_ema(close_prices, slow_period)
    diff = ema_fast - ema_slow
    dea = calculate_ema(diff, signal_period)
    macd_histogram = (diff - dea) * 2
    
    return diff, dea, macd_histogram


def calculate_macd_talib(close_prices: np.ndarray, 
                         fast_period: int = 12, 
                         slow_period: int = 26, 
                         signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    使用talib库计算MACD指标
    """
    import talib
    
    diff, dea, macd_histogram = talib.MACD(
        close_prices.astype(np.float64),
        fastperiod=fast_period,
        slowperiod=slow_period,
        signalperiod=signal_period
    )
    
    return diff, dea, macd_histogram


def calculate_macd(df: pd.DataFrame, 
                   price_column: str = 'close_price',
                   fast_period: Optional[int] = None,
                   slow_period: Optional[int] = None,
                   signal_period: Optional[int] = None) -> pd.DataFrame:
    """
    计算MACD指标并添加到DataFrame
    """
    if fast_period is None:
        fast_period = MACD_CONFIG['fast_period']
    if slow_period is None:
        slow_period = MACD_CONFIG['slow_period']
    if signal_period is None:
        signal_period = MACD_CONFIG['signal_period']
    
    result_df = df.copy()
    close_prices = df[price_column].values
    
    if TALIB_AVAILABLE:
        diff, dea, macd_histogram = calculate_macd_talib(
            close_prices, fast_period, slow_period, signal_period
        )
        result_df['DIFF'] = diff
        result_df['DEA'] = dea
        result_df['MACD'] = macd_histogram
    else:
        diff, dea, macd_histogram = calculate_macd_manual(
            df[price_column], fast_period, slow_period, signal_period
        )
        result_df['DIFF'] = diff
        result_df['DEA'] = dea
        result_df['MACD'] = macd_histogram
    
    return result_df


def is_golden_cross(diff: float, dea: float, 
                   prev_diff: float, prev_dea: float) -> bool:
    """
    判断是否为金叉（DIFF上穿DEA）
    """
    return (diff > dea) and (prev_diff <= prev_dea)


def is_dead_cross(diff: float, dea: float, 
                 prev_diff: float, prev_dea: float) -> bool:
    """
    判断是否为死叉（DIFF下穿DEA）
    """
    return (diff < dea) and (prev_diff >= prev_dea)


def check_macd_conditions(df: pd.DataFrame, 
                          require_diff_above_zero: bool = True,
                          require_dea_above_zero: bool = True,
                          require_golden_cross: bool = True) -> Tuple[bool, dict]:
    """
    检查MACD条件
    """
    if len(df) < 2:
        return False, {'error': '数据不足，需要至少2行数据'}
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    conditions = {
        'diff_above_zero': latest['DIFF'] > 0 if require_diff_above_zero else True,
        'dea_above_zero': latest['DEA'] > 0 if require_dea_above_zero else True,
        'golden_cross': is_golden_cross(
            latest['DIFF'], latest['DEA'],
            prev['DIFF'], prev['DEA']
        ) if require_golden_cross else True
    }
    
    all_satisfied = all(conditions.values())
    
    return all_satisfied, conditions


def find_latest_golden_cross(df: pd.DataFrame) -> Optional[dict]:
    """
    找到历史上最近一次满足条件的金叉点
    条件：DIFF > 0, DEA > 0, 且DIFF上穿DEA（金叉）
    
    Args:
        df: 包含MACD指标的DataFrame
    
    Returns:
        最近一次金叉点信息，如果没有找到则返回None
    """
    if len(df) < 2:
        return None
    
    # 从后往前找，找到最近的一次金叉
    for i in range(len(df) - 1, 0, -1):
        current = df.iloc[i]
        prev = df.iloc[i - 1]
        
        # 检查是否满足金叉条件
        if (current['DIFF'] > 0 and 
            current['DEA'] > 0 and 
            is_golden_cross(current['DIFF'], current['DEA'],
                          prev['DIFF'], prev['DEA'])):
            return {
                'date': current['trade_date'],
                'price': float(current['close_price']),
                'diff': current['DIFF'],
                'dea': current['DEA'],
                'macd': current['MACD'],
                'index': i
            }
    
    return None


def find_sell_point(df: pd.DataFrame, buy_idx: int) -> Optional[dict]:
    """
    找到卖出点
    卖出条件：买入后，MACD开始下降的那一天卖出
    （当天MACD值低于前一天的值）
    
    Args:
        df: 包含MACD指标的DataFrame
        buy_idx: 买入点在DataFrame中的索引
    
    Returns:
        卖出点信息
    """
    # 从买入点之后开始找
    for i in range(buy_idx + 1, len(df)):
        current = df.iloc[i]
        prev = df.iloc[i - 1]
        
        # MACD开始下降（即当天MACD < 前一天MACD）
        if pd.notna(current['MACD']) and pd.notna(prev['MACD']):
            if current['MACD'] < prev['MACD']:
                return {
                    'date': current['trade_date'],
                    'price': float(current['close_price']),
                    'diff': current['DIFF'],
                    'dea': current['DEA'],
                    'macd': current['MACD'],
                    'index': i
                }
    
    return None


def backtest_single_stock(df: pd.DataFrame) -> Optional[dict]:
    """
    对单支股票进行回测
    只找历史上最近一次满足条件的金叉点进行回测
    
    Args:
        df: 包含MACD指标的DataFrame
    
    Returns:
        回测结果
    """
    # 找到最近一次金叉点
    buy_point = find_latest_golden_cross(df)
    
    if not buy_point:
        return None
    
    # 找到卖出点
    sell_point = find_sell_point(df, buy_point['index'])
    
    if not sell_point:
        return None
    
    # 计算收益率
    buy_price = buy_point['price']
    sell_price = sell_point['price']
    return_rate = ((sell_price - buy_price) / buy_price) * 100
    
    return {
        'buy_date': buy_point['date'],
        'buy_price': buy_price,
        'buy_index': buy_point['index'],
        'buy_diff': buy_point['diff'],
        'buy_dea': buy_point['dea'],
        'sell_date': sell_point['date'],
        'sell_price': sell_price,
        'sell_index': sell_point['index'],
        'return_rate': return_rate,
        'holding_days': (sell_point['date'] - buy_point['date']).days
    }


def find_buy_signal(df: pd.DataFrame) -> Optional[dict]:
    """
    找到最近的买入信号点
    """
    return find_latest_golden_cross(df)


def find_golden_cross(df: pd.DataFrame) -> Optional[dict]:
    """
    找到最近的买入信号点（find_latest_golden_cross 的别名）
    """
    return find_latest_golden_cross(df)


def find_sell_point_old(df: pd.DataFrame, buy_date: pd.Timestamp) -> Optional[dict]:
    """
    找到卖出点（买入点之后DIFF-DEA值最大的点）
    """
    after_buy = df[df['trade_date'] > buy_date].copy()
    
    if after_buy.empty:
        return None
    
    after_buy['diff_dea_diff'] = after_buy['DIFF'] - after_buy['DEA']
    
    max_idx = after_buy['diff_dea_diff'].idxmax()
    max_row = after_buy.loc[max_idx]
    
    return {
        'date': max_row['trade_date'],
        'price': float(max_row['close_price']),
        'diff': max_row['DIFF'],
        'dea': max_row['DEA'],
        'diff_dea_diff': max_row['diff_dea_diff']
    }
