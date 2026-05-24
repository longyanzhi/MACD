"""
完整策略回测模块
包括选股、买入、持有、卖出全流程
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
from macd_calculator import calculate_macd, is_golden_cross


# 手续费率配置
COMMISSION_RATE = 0.0003  # 手续费约万三（双向收费）
STAMP_TAX_RATE = 0.001    # 印花税千分之一（卖出时收取）


class StrategyBacktest:
    """完整策略回测"""
    
    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.trades = []
        self.current_capital = initial_capital
    
    def calculate_commission(self, price: float, shares: int, is_sell: bool = False) -> Tuple[float, float]:
        """
        计算手续费
        
        Args:
            price: 成交价格
            shares: 成交股数
            is_sell: 是否为卖出
        
        Returns:
            (手续费, 印花税)
        """
        turnover = float(price) * int(shares)
        commission = turnover * COMMISSION_RATE
        # 印花税仅卖出时收取，最低5元
        stamp_tax = turnover * STAMP_TAX_RATE if is_sell else 0
        stamp_tax = max(stamp_tax, 5) if stamp_tax > 0 else 0
        
        # 手续费最低5元
        commission = max(commission, 5)
        
        return commission, stamp_tax
    
    def buy_stock(self, price: float, shares: int) -> Dict:
        """
        买入股票
        
        Args:
            price: 买入价格
            shares: 买入股数（100的整数倍）
        
        Returns:
            交易记录
        """
        turnover = float(price) * int(shares)
        commission, stamp_tax = self.calculate_commission(price, shares, is_sell=False)
        total_cost = turnover + commission
        
        self.current_capital -= total_cost
        
        return {
            'type': 'buy',
            'price': float(price),
            'shares': shares,
            'turnover': turnover,
            'commission': commission,
            'stamp_tax': 0,
            'total_cost': total_cost,
            'remaining_capital': self.current_capital
        }
    
    def sell_stock(self, price: float, shares: int) -> Dict:
        """
        卖出股票
        
        Args:
            price: 卖出价格
            shares: 卖出股数
        
        Returns:
            交易记录
        """
        turnover = float(price) * int(shares)
        commission, stamp_tax = self.calculate_commission(price, shares, is_sell=True)
        total_proceeds = turnover - commission - stamp_tax
        
        self.current_capital += total_proceeds
        
        return {
            'type': 'sell',
            'price': float(price),
            'shares': shares,
            'turnover': turnover,
            'commission': commission,
            'stamp_tax': stamp_tax,
            'total_proceeds': total_proceeds,
            'remaining_capital': self.current_capital
        }
    
    def find_macd_decline_point(self, df: pd.DataFrame, start_idx: int) -> Optional[Dict]:
        """
        找到MACD开始下降的点
        
        Args:
            df: 包含MACD指标的DataFrame
            start_idx: 起始索引（买入点之后）
        
        Returns:
            卖出点信息
        """
        for i in range(start_idx + 1, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i - 1]
            
            if pd.notna(current['MACD']) and pd.notna(prev['MACD']):
                if current['MACD'] < prev['MACD']:
                    return {
                        'date': current['trade_date'],
                        'price': float(current['close_price']),
                        'macd': current['MACD'],
                        'index': i
                    }
        return None
    
    def backtest_strategy(self, stock_code: str, df: pd.DataFrame, 
                          buy_date: pd.Timestamp, buy_price: float) -> Dict:
        """
        回测单次完整交易
        
        Args:
            stock_code: 股票代码
            df: 包含MACD指标的DataFrame
            buy_date: 买入日期
            buy_price: 买入价格
        
        Returns:
            回测结果
        """
        # 找到买入点在DataFrame中的索引
        buy_row = df[df['trade_date'] == buy_date]
        if buy_row.empty:
            return None
        buy_idx = buy_row.index[0]
        
        # 计算可买入的股数（100的整数倍）
        max_shares = int(self.initial_capital / buy_price / 100) * 100
        if max_shares < 100:
            return None
        
        # 买入
        buy_trade = self.buy_stock(buy_price, max_shares)
        buy_trade['date'] = buy_date
        buy_trade['stock_code'] = stock_code
        
        # 找到卖出点
        sell_point = self.find_macd_decline_point(df, buy_idx)
        
        if not sell_point:
            # 如果没有找到卖出点（MACD一直未下降），则不进行交易
            return None
        
        # 卖出
        sell_trade = self.sell_stock(sell_point['price'], max_shares)
        sell_trade['date'] = sell_point['date']
        sell_trade['stock_code'] = stock_code
        
        # 计算收益率
        total_cost = buy_trade['total_cost']
        total_proceeds = sell_trade['total_proceeds']
        profit = total_proceeds - total_cost
        return_rate = (profit / total_cost) * 100
        
        # 计算持有天数
        holding_days = (sell_point['date'] - buy_date).days if hasattr(sell_point['date'], 'days') else 0
        
        return {
            'stock_code': stock_code,
            'buy_date': buy_date,
            'buy_price': buy_price,
            'buy_shares': max_shares,
            'buy_commission': buy_trade['commission'],
            'sell_date': sell_point['date'],
            'sell_price': sell_point['price'],
            'sell_commission': sell_trade['commission'],
            'sell_stamp_tax': sell_trade['stamp_tax'],
            'total_cost': total_cost,
            'total_proceeds': total_proceeds,
            'profit': profit,
            'return_rate': return_rate,
            'holding_days': holding_days,
            'final_capital': self.current_capital
        }
    
    def run_backtest(self, stock_code: str, df: pd.DataFrame) -> Optional[Dict]:
        """
        运行完整策略回测
        
        Args:
            stock_code: 股票代码
            df: 包含MACD指标的DataFrame（需要已计算MACD）
        
        Returns:
            回测结果
        """
        if len(df) < 34:
            return None
        
        # 重置资金
        self.current_capital = self.initial_capital
        
        # 找到最近一次满足条件的金叉点
        buy_point = None
        for i in range(len(df) - 1, 0, -1):
            current = df.iloc[i]
            prev = df.iloc[i - 1]
            
            if (current['DIFF'] > 0 and 
                current['DEA'] > 0 and 
                is_golden_cross(current['DIFF'], current['DEA'],
                              prev['DIFF'], prev['DEA'])):
                buy_point = {
                    'date': current['trade_date'],
                    'price': current['close_price']
                }
                break
        
        if not buy_point:
            return None
        
        # 执行回测
        result = self.backtest_strategy(stock_code, df, buy_point['date'], buy_point['price'])
        return result
    
    def print_result(self, result: Dict):
        """打印回测结果"""
        if not result:
            print("回测失败")
            return
        
        print("\n" + "="*60)
        print("完整策略回测结果")
        print("="*60)
        print(f"股票代码: {result['stock_code']}")
        print(f"\n【买入】")
        print(f"  日期: {result['buy_date'].date() if hasattr(result['buy_date'], 'date') else result['buy_date']}")
        print(f"  价格: {result['buy_price']:.2f}")
        print(f"  股数: {result['buy_shares']}")
        print(f"  手续费: {result['buy_commission']:.2f}")
        print(f"\n【卖出】")
        print(f"  日期: {result['sell_date'].date() if hasattr(result['sell_date'], 'date') else result['sell_date']}")
        print(f"  价格: {result['sell_price']:.2f}")
        print(f"  手续费: {result['sell_commission']:.2f}")
        print(f"  印花税: {result['sell_stamp_tax']:.2f}")
        print(f"\n【统计】")
        print(f"  买入总成本: {result['total_cost']:.2f}")
        print(f"  卖出总收益: {result['total_proceeds']:.2f}")
        print(f"  盈利金额: {result['profit']:.2f}")
        print(f"  收益率: {result['return_rate']:.2f}%")
        print(f"  持仓天数: {result['holding_days']}天")
        print(f"  最终资金: {result['final_capital']:.2f}")
        print("="*60)


def run_full_backtest(stock_results: List[Dict]) -> List[Dict]:
    """
    对筛选出的股票进行完整策略回测
    
    Args:
        stock_results: 筛选结果 [{'stock_code': xxx, 'data': df}, ...]
    
    Returns:
        所有股票的回测结果
    """
    all_results = []
    
    print(f"\n开始完整策略回测 ({len(stock_results)} 支股票)...")
    print("="*60)
    
    for i, item in enumerate(stock_results, 1):
        stock_code = item['stock_code']
        df = item['data']
        
        if i % 100 == 0 or i == 1:
            progress = int((i / len(stock_results)) * 100)
            print(f"正在回测 {i}/{len(stock_results)} 支股票... ({progress}%)")
        
        backtest = StrategyBacktest(initial_capital=10000)
        result = backtest.run_backtest(stock_code, df)
        
        if result:
            all_results.append(result)
    
    print("="*60)
    
    if all_results:
        # 按收益率排序
        all_results.sort(key=lambda x: x['return_rate'], reverse=True)
        return all_results
    
    return []


def print_backtest_summary(results: List[Dict], top_n: int = 20):
    """打印回测摘要"""
    if not results:
        print("没有可显示的回测结果")
        return
    
    print("\n" + "="*100)
    print("完整策略回测结果摘要（初始资金: 10000元，含手续费）")
    print("="*100)
    print(f"{'排名':<4} {'股票代码':<12} {'买入日期':<12} {'买入价':<10} {'卖出日期':<12} {'卖出价':<10} {'收益率':<10} {'盈利':<10} {'持仓天':<8}")
    print("-"*100)
    
    for i, result in enumerate(results[:top_n], 1):
        buy_date = result['buy_date'].date() if hasattr(result['buy_date'], 'date') else result['buy_date']
        sell_date = result['sell_date'].date() if hasattr(result['sell_date'], 'date') else result['sell_date']
        
        print(f"{i:<4} {result['stock_code']:<12} "
              f"{str(buy_date):<12} "
              f"{result['buy_price']:<10.2f} "
              f"{str(sell_date):<12} "
              f"{result['sell_price']:<10.2f} "
              f"{result['return_rate']:<10.2f}% "
              f"{result['profit']:<10.2f} "
              f"{result['holding_days']:<8}")
    
    print("="*100)
