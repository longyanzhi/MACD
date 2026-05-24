"""检查数据库表结构"""
import psycopg2
from config import DB_CONFIG

def check_table_structure(table_name):
    """检查指定表的详细结构"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        print(f"\n{'='*70}")
        print(f"表: {table_name}")
        print(f"{'='*70}")
        
        # 获取列信息
        cursor.execute(f"""
            SELECT 
                column_name, 
                data_type, 
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """)
        
        columns = cursor.fetchall()
        print(f"\n列信息:")
        for col_name, col_type, nullable, default in columns:
            null_str = "NULL" if nullable == 'YES' else "NOT NULL"
            default_str = f" DEFAULT {default}" if default else ""
            print(f"  {col_name}: {col_type} {null_str}{default_str}")
        
        # 获取记录数
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        print(f"\n总记录数: {count:,}")
        
        # 获取样本数据
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
        rows = cursor.fetchall()
        print(f"\n样本数据 (前3条):")
        for i, row in enumerate(rows):
            print(f"  {i+1}. {row}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"检查表 {table_name} 时出错: {e}")

def main():
    # 检查可能相关的表
    tables_to_check = [
        'trade_history_daily',  # 日线数据
        'stock_basic',          # 股票基本信息
        'daily_basic',          # 每日基本面
    ]
    
    for table in tables_to_check:
        check_table_structure(table)

if __name__ == "__main__":
    main()
