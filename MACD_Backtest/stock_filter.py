"""
股票筛选模块
根据MACD指标条件筛选股票
使用批量查询优化性能
"""

import pandas as pd
from typing import List, Dict, Any
from database import get_stock_data_batch, get_all_stocks, get_latest_trade_date
from macd_calculator import calculate_macd, check_macd_conditions
from config import FILTER_CONFIG


class StockFilter:
    """股票筛选器（优化版）"""
    
    def __init__(self):
        self.latest_date = None
        self.filtered_stocks = []
        self.all_data = None
    
    def get_filtered_stocks(self, 
                          require_diff_above_zero: bool = None,
                          require_dea_above_zero: bool = None,
                          require_golden_cross: bool = None,
                          show_progress: bool = True) -> List[str]:
        """
        筛选满足条件的股票（批量查询优化版）
        
        Args:
            require_diff_above_zero: DIFF是否需要大于0
            require_dea_above_zero: DEA是否需要大于0
            require_golden_cross: 是否需要金叉条件
            show_progress: 是否显示进度条
        
        Returns:
            满足条件的股票代码列表
        """
        if require_diff_above_zero is None:
            require_diff_above_zero = FILTER_CONFIG['diff_above_zero']
        if require_dea_above_zero is None:
            require_dea_above_zero = FILTER_CONFIG['dea_above_zero']
        if require_golden_cross is None:
            require_golden_cross = FILTER_CONFIG['golden_cross']
        
        # 获取最新交易日期
        self.latest_date = get_latest_trade_date()
        if not self.latest_date:
            print("未找到交易日期")
            return []
        
        print(f"最新交易日期: {self.latest_date}")
        
        # 获取所有股票
        all_stocks = get_all_stocks(self.latest_date)
        total_stocks = len(all_stocks)
        print(f"今日共有 {total_stocks} 支股票有数据")
        
        # 批量获取所有股票数据
        print("\n正在批量获取股票数据...")
        self.all_data = get_stock_data_batch(all_stocks, end_date=self.latest_date)
        print(f"已获取 {len(self.all_data)} 条交易记录")
        
        # 按股票分组处理
        print("\n正在计算MACD指标...")
        stock_codes = self.all_data['stock_code'].unique()
        total = len(stock_codes)
        
        filtered = []
        last_print_count = 0
        
        for idx, stock_code in enumerate(stock_codes):
            # 每处理10%打印一次进度
            if show_progress and (idx - last_print_count >= max(1, total // 10) or idx == 0):
                progress = int((idx / total) * 100)
                print(f"\r进度: {idx}/{total} ({progress}%)", end='', flush=True)
                last_print_count = idx
            
            # 获取该股票的数据
            df = self.all_data[self.all_data['stock_code'] == stock_code].copy()
            
            if len(df) < 34:
                continue
            
            # 计算MACD指标
            df = calculate_macd(df)
            
            # 检查是否满足条件
            is_valid, conditions = check_macd_conditions(
                df,
                require_diff_above_zero=require_diff_above_zero,
                require_dea_above_zero=require_dea_above_zero,
                require_golden_cross=require_golden_cross
            )
            
            if is_valid:
                filtered.append({
                    'stock_code': stock_code,
                    'data': df
                })
        
        print(f"\r进度: {total}/{total} (100%)")
        
        self.filtered_stocks = filtered
        print(f"\n筛选完成: 共 {len(filtered)} 支股票满足条件")
        return [item['stock_code'] for item in filtered]
    
    def get_filtered_stocks_with_data(self) -> List[Dict[str, Any]]:
        """
        获取筛选结果及完整数据（用于回测）
        
        Returns:
            包含股票代码和MACD计算后数据的列表
        """
        if not self.filtered_stocks:
            self.get_filtered_stocks()
        return self.filtered_stocks
