"""
数据库配置文件
请根据您的实际数据库环境修改以下配置
"""

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool


# 数据库连接配置
DB_CONFIG = {
    'host': 'frp-cat.com',           # 数据库主机地址
    'port': 34497,                  # 数据库端口
    'database': 'tsdbstock',        # 数据库名称
    'user': 'tsadmin',            # 数据库用户名
    'password': 'user6362964'   # 数据库密码
}

# Tushare 配置
TUSHARE_CONFIG = {
    'token': 'f8d313b7e099ffca1d87a7376b6d4b4ceca4b235326ff381f23a9de4',  # 替换为你的tushare token
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
