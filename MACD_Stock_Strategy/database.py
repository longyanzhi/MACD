"""
数据库连接和查询模块
使用 SQLAlchemy 连接池优化性能
增强稳定性：减小批量大小，添加重试机制
"""

import pandas as pd
import numpy as np
from typing import Optional, List, Dict
from sqlalchemy import text
from config import engine, TABLE_NAME
import time


def execute_with_retry(query, params, max_retries=3, retry_delay=1):
    """
    执行SQL查询，带重试机制
    
    Args:
        query: SQL查询语句
        params: 查询参数
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）
    
    Returns:
        查询结果
    """
    last_error = None
    
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                result = conn.execute(text(query), params)
                return result
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))  # 递增延迟
                continue
            raise last_error


def get_stock_data_batch(stock_codes: List[str], 
                        end_date: Optional[str] = None) -> pd.DataFrame:
    """
    批量获取多支股票的历史数据（优化版本）
    
    Args:
        stock_codes: 股票代码列表
        end_date: 结束日期 (格式: 'YYYY-MM-DD')
    
    Returns:
        包含所有股票数据的DataFrame
    """
    if not stock_codes:
        return pd.DataFrame()
    
    # 减小批量大小以提高稳定性（从100降到20）
    batch_size = 20
    total_batches = (len(stock_codes) + batch_size - 1) // batch_size
    
    print(f"需要分 {total_batches} 批获取数据...")
    
    all_data = []
    
    for i in range(0, len(stock_codes), batch_size):
        batch_num = i // batch_size + 1
        batch = stock_codes[i:i + batch_size]
        placeholders = ','.join([f':code{j}' for j in range(len(batch))])
        
        query = f"""
            SELECT ts_code as stock_code, trade_date, open, high, low, close, vol
            FROM {TABLE_NAME}
            WHERE ts_code IN ({placeholders})
        """
        
        params = {f'code{j}': code for j, code in enumerate(batch)}
        
        if end_date:
            query += " AND trade_date <= :end_date"
            params['end_date'] = end_date
        
        query += " ORDER BY ts_code, trade_date ASC"
        
        # 显示每批进度
        print(f"\r正在获取第 {batch_num}/{total_batches} 批 ({batch_num * 100 // total_batches}%)...", end='', flush=True)
        
        try:
            result = execute_with_retry(query, params)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
            all_data.append(df)
        except Exception as e:
            print(f"\n  警告: 第 {batch_num} 批查询失败: {e}")
            # 单个失败不影响整体，继续下一批
    
    print(f"\r已完成 {total_batches}/{total_batches} 批 (100%)      ")
    
    if not all_data:
        return pd.DataFrame()
    
    result = pd.concat(all_data, ignore_index=True)
    result['trade_date'] = pd.to_datetime(result['trade_date'])
    result = result.rename(columns={
        'open': 'open_price',
        'high': 'high_price',
        'low': 'low_price',
        'close': 'close_price',
        'vol': 'volume'
    })
    for col in ['open_price', 'close_price', 'high_price', 'low_price', 'volume']:
        if col in result.columns:
            result[col] = result[col].astype(float)
    
    return result


def get_stock_data(stock_code: str, 
                   start_date: Optional[str] = None,
                   end_date: Optional[str] = None) -> pd.DataFrame:
    """
    获取指定股票的历史数据
    
    Args:
        stock_code: 股票代码 (格式: '000001.SZ')
        start_date: 开始日期 (格式: 'YYYY-MM-DD')
        end_date: 结束日期 (格式: 'YYYY-MM-DD')
    
    Returns:
        包含股票数据的DataFrame
    """
    query = f"""
        SELECT ts_code as stock_code, trade_date, open, high, low, close, vol
        FROM {TABLE_NAME}
        WHERE ts_code = :stock_code
    """
    params = {'stock_code': stock_code}
    
    if start_date:
        query += " AND trade_date >= :start_date"
        params['start_date'] = start_date
    
    if end_date:
        query += " AND trade_date <= :end_date"
        params['end_date'] = end_date
    
    query += " ORDER BY trade_date ASC"
    
    result = execute_with_retry(query, params)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.rename(columns={
        'open': 'open_price',
        'high': 'high_price',
        'low': 'low_price',
        'close': 'close_price',
        'vol': 'volume'
    })
    for col in ['open_price', 'close_price', 'high_price', 'low_price', 'volume']:
        if col in df.columns:
            df[col] = df[col].astype(np.float64)

    return df


def get_all_stocks(trade_date: Optional[str] = None) -> List[str]:
    """
    获取所有股票代码列表
    
    Args:
        trade_date: 交易日期（可选），如果指定则返回该日期有数据的股票
    
    Returns:
        股票代码列表
    """
    if trade_date:
        query = f"""
            SELECT DISTINCT ts_code
            FROM {TABLE_NAME} 
            WHERE trade_date = :trade_date
            ORDER BY ts_code
        """
        params = {'trade_date': trade_date}
    else:
        query = f"""
            SELECT DISTINCT ts_code
            FROM {TABLE_NAME}
            ORDER BY ts_code
        """
        params = {}
    
    result = execute_with_retry(query, params)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    
    return df['ts_code'].tolist()


def get_latest_trade_date() -> Optional[str]:
    """
    获取数据库中最新的交易日期
    
    Returns:
        最新交易日期字符串 (格式: 'YYYY-MM-DD')
    """
    query = f"""
        SELECT MAX(trade_date) as latest_date 
        FROM {TABLE_NAME}
    """
    
    result = execute_with_retry(query, {})
    row = result.fetchone()
    
    if row and row[0] is not None:
        return row[0].strftime('%Y-%m-%d')
    return None


def get_stock_count() -> int:
    """
    获取数据库中的股票总数
    
    Returns:
        股票数量
    """
    query = f"""
        SELECT COUNT(DISTINCT ts_code) as count 
        FROM {TABLE_NAME}
    """
    
    result = execute_with_retry(query, {})
    row = result.fetchone()
    
    return row[0] if row else 0


def get_stock_name(stock_code: str) -> Optional[str]:
    """
    获取股票名称
    
    Args:
        stock_code: 股票代码 (格式: '000001.SZ')
    
    Returns:
        股票名称，如果没有则返回 None
    """
    query = """
        SELECT name
        FROM stock_basic
        WHERE ts_code = :stock_code
        LIMIT 1
    """
    
    try:
        result = execute_with_retry(query, {'stock_code': stock_code})
        row = result.fetchone()
        if row and row[0]:
            return row[0]
        return None
    except Exception:
        return None


def get_all_stock_names() -> Dict[str, str]:
    """
    获取所有股票代码到名称的映射
    
    Returns:
        {stock_code: name} 字典
    """
    query = "SELECT ts_code, name FROM stock_basic"
    
    try:
        result = execute_with_retry(query, {})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        return dict(zip(df['ts_code'], df['name']))
    except Exception:
        return {}


def check_table_exists() -> bool:
    """
    检查数据表是否存在
    
    Returns:
        表是否存在
    """
    query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = :table_name
        )
    """
    
    result = execute_with_retry(query, {"table_name": TABLE_NAME})
    exists = result.scalar()
    
    return exists


def load_all_stock_data(start_date: Optional[str] = None, 
                        end_date: Optional[str] = None) -> dict:
    """
    加载指定日期范围的股票数据
    
    Args:
        start_date: 开始日期 (格式: 'YYYY-MM-DD')，如果为None则从end_date往前推1个月
        end_date: 结束日期，如果为None则加载最新日期
    
    Returns:
        dict: {stock_code: DataFrame} 格式，按股票代码分组的字典
    """
    if end_date is None:
        end_date = get_latest_trade_date()
    
    if start_date is None:
        end_dt = pd.to_datetime(end_date)
        start_dt = end_dt - pd.Timedelta(days=60)
        start_date = start_dt.strftime('%Y-%m-%d')
    
    if not end_date:
        return {}
    
    query = f"""
        SELECT ts_code, trade_date, open, high, low, close, vol
        FROM {TABLE_NAME}
        WHERE trade_date >= :start_date AND trade_date <= :end_date
        ORDER BY ts_code, trade_date
    """
    
    result = execute_with_retry(query, {"start_date": start_date, "end_date": end_date})
    
    # 先获取列名，再获取数据
    columns = list(result.keys())
    rows = result.fetchall()
    
    if not rows:
        return {}
    
    df = pd.DataFrame(rows, columns=columns)
    
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df = df.rename(columns={
        'ts_code': 'stock_code',
        'open': 'open_price',
        'high': 'high_price',
        'low': 'low_price',
        'close': 'close_price',
        'vol': 'volume'
    })
    for col in ['open_price', 'close_price', 'high_price', 'low_price', 'volume']:
        if col in df.columns:
            df[col] = df[col].astype(float)
    
    # 按股票代码分组
    return {code: group.reset_index(drop=True) for code, group in df.groupby('stock_code')}
