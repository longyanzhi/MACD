"""
数据库连接和查询模块
使用 SQLAlchemy 连接池优化性能
增强稳定性：减小批量大小，添加重试机制
"""

import pandas as pd
from typing import Optional, List, Dict
from sqlalchemy import text
from config import engine, TABLE_NAME
import time


def execute_with_retry(query, params, max_retries=3, retry_delay=1):
    """
    执行SQL查询，带重试机制
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
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise last_error


def get_stock_data(query, params=None) -> pd.DataFrame:
    """直接执行SQL查询"""
    try:
        result = execute_with_retry(query, params or {})
        if result is None:
            return pd.DataFrame()
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        if 'trade_date' in df.columns:
            df['trade_date'] = pd.to_datetime(df['trade_date'])
        return df
    except Exception as e:
        print(f"查询错误: {e}")
        return pd.DataFrame()


def get_all_stocks(trade_date: Optional[str] = None) -> List[str]:
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


def get_stock_count() -> int:
    query = f"SELECT COUNT(DISTINCT ts_code) as count FROM {TABLE_NAME}"
    result = execute_with_retry(query, {})
    row = result.fetchone()
    return row[0] if row else 0


def get_stock_name(stock_code: str) -> Optional[str]:
    query = """
        SELECT name FROM stock_basic WHERE ts_code = :stock_code LIMIT 1
    """
    try:
        result = execute_with_retry(query, {'stock_code': stock_code})
        row = result.fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def get_all_stock_names() -> Dict[str, str]:
    query = "SELECT ts_code, name FROM stock_basic"
    try:
        result = execute_with_retry(query, {})
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
        return dict(zip(df['ts_code'], df['name']))
    except Exception:
        return {}


def check_table_exists() -> bool:
    query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = :table_name
        )
    """
    result = execute_with_retry(query, {"table_name": TABLE_NAME})
    exists = result.scalar()
    return exists
