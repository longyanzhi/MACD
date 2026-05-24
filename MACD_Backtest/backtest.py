"""
回测引擎模块
对筛选出的股票进行回测，计算收益率
策略逻辑：
1. 筛选出满足 MACD 条件的股票（可能几十支）
2. 对每只股票，找到历史上最近一次满足条件的金叉点
3. 对这个最近的金叉点进行买入-卖出回测
4. 从这几十支股票中选择收益率最高的
"""

import pandas as pd
from typing import List, Optional, Dict
from macd_calculator import calculate_macd, backtest_single_stock


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self):
        self.results = []
    
    def backtest_stock(self, stock_code: str, df: pd.DataFrame) -> Optional[Dict]:
        """
        对单支股票进行回测
        只找历史上最近一次满足条件的金叉点进行回测
        
        Args:
            stock_code: 股票代码
            df: 包含MACD指标的DataFrame
        
        Returns:
            回测结果
        """
        if len(df) < 34:
            return None
        
        result = backtest_single_stock(df)
        
        if result:
            result['stock_code'] = stock_code
            return result
        
        return None
    
    def backtest_multiple_stocks(self, stock_results: List[Dict]) -> List[Dict]:
        """
        对多支股票进行回测
        
        Args:
            stock_results: 包含股票代码和对应数据的列表
                          格式: [{'stock_code': '000001.SZ', 'data': DataFrame}, ...]
        
        Returns:
            所有股票回测结果列表
        """
        self.results = []
        
        print(f"\n开始回测 {len(stock_results)} 支股票...")
        print("="*60)
        
        for i, item in enumerate(stock_results, 1):
            stock_code = item['stock_code']
            df = item['data']
            
            # 显示进度
            if i % 100 == 0 or i == 1:
                progress = int((i / len(stock_results)) * 100)
                print(f"正在回测 {i}/{len(stock_results)} 支股票... ({progress}%)")
            
            result = self.backtest_stock(stock_code, df)
            
            if result:
                self.results.append(result)
        
        # 按收益率排序
        self.results.sort(key=lambda x: x['return_rate'], reverse=True)
        
        print("="*60)
        print(f"回测完成，共 {len(self.results)} 支股票有有效交易")
        
        return self.results
    
    def get_best_stock(self) -> Optional[Dict]:
        """获取收益率最高的股票"""
        if not self.results:
            return None
        return self.results[0]
    
    def get_top_n(self, n: int = 10) -> List[Dict]:
        """获取收益率前N名的股票"""
        return self.results[:n]
    
    def print_summary(self, top_n: int = 20):
        """打印回测结果摘要"""
        if not self.results:
            print("没有可显示的回测结果")
            return
        
        print("\n" + "="*80)
        print("回测结果摘要（每只股票取历史上最近一次金叉点回测）")
        print("="*80)
        print(f"{'排名':<4} {'股票代码':<12} {'买入日期':<12} {'买入价':<10} {'卖出日期':<12} {'卖出价':<10} {'收益率':<10} {'持仓天数':<8}")
        print("-"*80)
        
        for i, result in enumerate(self.results[:top_n], 1):
            buy_date_str = str(result['buy_date'].date()) if hasattr(result['buy_date'], 'date') else str(result['buy_date'])
            sell_date_str = str(result['sell_date'].date()) if hasattr(result['sell_date'], 'date') else str(result['sell_date'])
            
            print(f"{i:<4} {result['stock_code']:<12} "
                  f"{buy_date_str:<12} "
                  f"{result['buy_price']:<10.2f} "
                  f"{sell_date_str:<12} "
                  f"{result['sell_price']:<10.2f} "
                  f"{result['return_rate']:<10.2f}% "
                  f"{result['holding_days']:<8}")
        
        print("="*80)
        
        if self.results:
            best = self.get_best_stock()
            print(f"\n最佳股票: {best['stock_code']}")
            print(f"收益率: {best['return_rate']:.2f}%")
            print(f"买入日期: {best['buy_date'].date() if hasattr(best['buy_date'], 'date') else best['buy_date']}")
            print(f"买入价格: {best['buy_price']:.2f}")
            print(f"卖出日期: {best['sell_date'].date() if hasattr(best['sell_date'], 'date') else best['sell_date']}")
            print(f"卖出价格: {best['sell_price']:.2f}")
            print(f"持仓天数: {best['holding_days']}天")
