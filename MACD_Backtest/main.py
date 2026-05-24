"""
MACD股票筛选回测系统 - 主程序
月度/年度回测版

策略说明:
1. 选股条件: DIFF > 0, DEA > 0, 且出现金叉（DIFF上穿DEA）
2. 过滤条件: 主板股票, 前一日MACD<0, 前5日MACD不为持续很小, 非涨停, 非ST
3. 循环交易:
   - 买入: 金叉当天开盘价买入
   - 卖出: 买入后MACD开始下降的那一天卖出
   - 卖出后立即重新选股买入
4. 初始资金: 10000元
5. 手续费: 万三双向 + 印花税千一（卖出）
6. 回测周期: 2025年全年（逐月回测）
"""

import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from calendar import monthrange
from database import get_stock_data, check_table_exists, get_stock_count, execute_with_retry
from macd_calculator import calculate_macd
from monthly_backtest import run_monthly_backtest
from config import TABLE_NAME, MACD_CONFIG


# 回测年份配置（修改这里即可回测不同年份）
BACKTEST_YEAR = 2024


def print_banner():
    """打印系统标题"""
    print("\n" + "="*80)
    print("MACD股票筛选回测系统 - 年度回测版")
    print("="*80)
    print("策略说明:")
    print("1. 选股条件: DIFF > 0, DEA > 0, 且出现金叉（DIFF上穿DEA）")
    print("2. 过滤条件: 主板股票, 前一日MACD<0, 非涨停, 非ST")
    print("3. 循环交易: 买入 → 卖出 → 立即重新选股买入 → 循环")
    print("4. 买入: 金叉当天开盘价买入")
    print("5. 卖出: 买入后MACD开始下降的那一天卖出（收盘价）")
    print("6. 初始资金: 10000元/每月")
    print("7. 手续费: 万三双向收费 + 印花税千一（卖出时）")
    print("="*80 + "\n")


def get_month_date_range(year: int, month: int) -> tuple:
    """获取指定年月的日期范围"""
    _, last_day = monthrange(year, month)
    start_date = f"{year}-{month:02d}-01"
    end_date = f"{year}-{month:02d}-{last_day:02d}"
    return start_date, end_date


def get_year_months(year: int) -> list:
    """获取一年的所有月份"""
    return [(year, m) for m in range(1, 13)]


def load_all_stock_data_with_macd():
    """
    加载所有股票数据并计算MACD（只加载一次，供全年复用）
    """
    print("正在加载股票数据...")

    query = f"""
        SELECT DISTINCT ts_code
        FROM {TABLE_NAME}
        ORDER BY ts_code
    """
    stock_codes_df = get_stock_data(query)
    stock_codes = stock_codes_df['ts_code'].tolist()

    print(f"共 {len(stock_codes)} 支股票，开始加载...")

    stock_data = {}
    batch_size = 50
    total_batches = (len(stock_codes) + batch_size - 1) // batch_size

    for i in range(0, len(stock_codes), batch_size):
        batch_codes = stock_codes[i:i + batch_size]
        batch_num = i // batch_size + 1

        placeholders = ','.join([f"'{code}'" for code in batch_codes])
        query = f"""
            SELECT ts_code as stock_code, trade_date, open, close
            FROM {TABLE_NAME}
            WHERE ts_code IN ({placeholders})
            ORDER BY ts_code, trade_date
        """

        df = get_stock_data(query)
        if df is None or df.empty:
            continue

        df = df.rename(columns={'open': 'open_price', 'close': 'close_price'})
        for col in ['open_price', 'close_price', 'high', 'low', 'vol']:
            if col in df.columns:
                df[col] = df[col].astype(np.float64)

        for stock_code in df['stock_code'].unique():
            stock_df = df[df['stock_code'] == stock_code].copy()
            stock_df = stock_df.sort_values('trade_date')
            stock_df = calculate_macd(stock_df)
            stock_data[stock_code] = stock_df

        print(f"\r加载进度: {batch_num}/{total_batches} ({batch_num * 100 // total_batches}%)", end='', flush=True)

    print(f"\n已加载 {len(stock_data)} 支股票数据")
    return stock_data


def get_stock_data(query: str, params: dict = None) -> pd.DataFrame:
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


def filter_stocks_by_date(stock_data: dict, start_date: str, end_date: str) -> dict:
    """
    按日期筛选股票数据，只保留指定日期范围内的数据
    往前多取90天用于计算MACD和历史模拟
    """
    filtered = {}
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    for stock_code, df in stock_data.items():
        if not pd.api.types.is_datetime64_any_dtype(df['trade_date']):
            df = df.copy()
            df['trade_date'] = pd.to_datetime(df['trade_date'])

        extended_start = start_dt - pd.Timedelta(days=90)
        mask = (df['trade_date'] >= extended_start) & (df['trade_date'] <= end_dt)
        filtered_df = df[mask].copy()

        if len(filtered_df) >= 34:
            filtered[stock_code] = filtered_df

    return filtered


def run_yearly_backtest(stock_data: dict, year: int):
    """
    逐月运行全年回测，每月独立初始资金10000元
    输出每月汇总 + 年度汇总
    """
    months = get_year_months(year)
    monthly_results = []
    year_start = f"{year}-01-01"
    year_end = f"{year}-12-31"

    print(f"\n{'='*80}")
    print(f"开始 {year} 年全年度回测")
    print(f"{'='*80}\n")

    for year_num, month_num in months:
        start_date, end_date = get_month_date_range(year_num, month_num)
        month_name = f"{year_num}年{month_num}月"

        stock_data_filtered = filter_stocks_by_date(stock_data, start_date, end_date)
        if not stock_data_filtered:
            print(f"[{month_name}] 无足够数据，跳过")
            continue

        print(f"\n{'='*80}")
        print(f"[{month_name}] 回测周期: {start_date} 至 {end_date}")
        print(f"有效股票数: {len(stock_data_filtered)}")
        print("-"*80)

        result = run_monthly_backtest(stock_data_filtered, start_date, end_date)
        monthly_results.append({
            'month': month_name,
            'year': year_num,
            'month_num': month_num,
            'start_date': start_date,
            'end_date': end_date,
            'initial_capital': result['initial_capital'],
            'final_capital': result['final_capital'],
            'total_profit': result['total_profit'],
            'total_return': result['total_return'],
            'trade_count': result['trade_count'],
            'winning_trades': result['winning_trades'],
            'losing_trades': result['losing_trades'],
            'win_rate': result['win_rate'],
            'avg_profit': result['avg_profit'],
        })

    # 年度汇总
    print_yearly_summary(monthly_results, year)
    return monthly_results


def print_yearly_summary(monthly_results: list, year: int):
    """打印年度汇总"""
    if not monthly_results:
        print(f"\n{year}年无有效回测结果")
        return

    total_return = sum(r['total_return'] for r in monthly_results)
    avg_monthly_return = total_return / len(monthly_results)
    total_trades = sum(r['trade_count'] for r in monthly_results)
    total_wins = sum(r['winning_trades'] for r in monthly_results)
    total_losses = sum(r['losing_trades'] for r in monthly_results)
    overall_win_rate = (total_wins / (total_wins + total_losses) * 100) if (total_wins + total_losses) > 0 else 0

    # 月度收益列表
    monthly_returns = [r['total_return'] for r in monthly_results]
    max_return = max(monthly_returns)
    min_return = min(monthly_returns)
    positive_months = sum(1 for r in monthly_returns if r > 0)
    negative_months = sum(1 for r in monthly_returns if r < 0)

    print(f"\n\n{'='*80}")
    print(f"{year} 年年度回测汇总")
    print(f"{'='*80}")
    print(f"回测月份数: {len(monthly_results)}")
    print("-"*80)
    print(f"{'月份':<12} {'初始资金':<12} {'最终资金':<12} {'盈利金额':<12} {'收益率':<10} {'交易次数':<8} {'胜率':<8}")
    print("-"*80)

    for r in monthly_results:
        print(f"{r['month']:<12} {r['initial_capital']:<12.2f} {r['final_capital']:<12.2f} "
              f"{r['total_profit']:<12.2f} {r['total_return']:<10.2f}% {r['trade_count']:<8} {r['win_rate']:<8.2f}%")

    print("-"*80)
    print(f"\n{'='*80}")
    print(f"年度统计")
    print(f"{'='*80}")
    print(f"平均月收益率: {avg_monthly_return:.2f}%")
    print(f"最高月收益率: {max_return:.2f}%")
    print(f"最低月收益率: {min_return:.2f}%")
    print(f"盈利月份数: {positive_months}/{len(monthly_results)}")
    print(f"亏损月份数: {negative_months}/{len(monthly_results)}")
    print(f"总交易次数: {total_trades}")
    print(f"总胜率: {overall_win_rate:.2f}% ({total_wins}胜/{total_losses}负)")
    print(f"{'='*80}")


def main():
    """主函数"""
    try:
        # ── 判断运行模式 ──
        if len(sys.argv) > 1 and sys.argv[1] == "--vn":
            return

        print_banner()

        print("正在检查数据库连接...")
        if not check_table_exists():
            print("错误: 数据表不存在或未正确配置")
            sys.exit(1)

        stock_count = get_stock_count()
        print(f"数据库连接正常，共 {stock_count} 支股票\n")

        # 加载所有股票数据（只加载一次）
        all_stock_data = load_all_stock_data_with_macd()

        if not all_stock_data:
            print("错误: 没有加载到股票数据")
            sys.exit(1)

        # 逐月运行全年回测
        run_yearly_backtest(all_stock_data, BACKTEST_YEAR)

    except KeyboardInterrupt:
        print("\n\n用户中断程序")
        sys.exit(0)
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
