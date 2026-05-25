"""
数据库配置文件
从环境变量读取敏感信息
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool


# 数据库连接配置（从环境变量读取）
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '5432')),
    'database': os.getenv('DB_NAME', 'tsdbstock'),
    'user': os.getenv('DB_USER', 'tsadmin'),
    'password': os.getenv('DB_PASSWORD', '')
}

# 创建 SQLAlchemy 引擎（带连接池）
DB_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

engine = create_engine(
    DB_URL,
    poolclass=QueuePool,
    pool_size=5,           # 连接池大小
    max_overflow=10,        # 最大溢出连接数
    pool_pre_ping=True,     # 连接前测试
    pool_recycle=3600,      # 一小时后回收连接
    echo=False              # 不打印SQL语句
)

# 表名配置
TABLE_NAME = 'stk_daily_qfq'

# MACD参数配置
MACD_CONFIG = {
    'fast_period': 12,     # 快速EMA周期
    'slow_period': 26,    # 慢速EMA周期
    'signal_period': 9     # Signal线周期
}

# 筛选条件配置
FILTER_CONFIG = {
    'diff_above_zero': True,      # DIFF是否需要大于0
    'dea_above_zero': True,       # DEA是否需要大于0
    'golden_cross': True          # 是否需要金叉条件
}
