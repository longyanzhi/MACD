"""
MACD股票筛选回测模块 - 月度版本
包含选股、买入、持有、卖出的完整流程
遍历至回测周期结束

过滤规则:
1. 主板股票过滤（沪市600/601/603/605，深市000/001）
2. 前一日MACD为负值
3. 前5日MACD不能一直很小
4. 前一日不能涨停
5. ST股不能买入
6. 买入用开盘价（考虑T日涨跌）
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
from macd_calculator import calculate_macd, is_golden_cross
from database import get_all_stock_names


COMMISSION_RATE = 0.0003
STAMP_TAX_RATE = 0.001


def is_main_board_stock(stock_code: str) -> bool:
    """
    判断是否为主板股票
    主板: 沪市600/601/603/605开头, 深市000/001开头
    排除: 科创板(688), 创业板(002/003)
    """
    if stock_code.endswith('.SH'):
        code = stock_code.replace('.SH', '')
        return code.startswith('600') or code.startswith('601') or \
               code.startswith('603') or code.startswith('605')
    elif stock_code.endswith('.SZ'):
        code = stock_code.replace('.SZ', '')
        return code.startswith('000') or code.startswith('001')
    return False


class MonthlyBacktest:
    """月度完整策略回测"""

    def __init__(self, initial_capital: float = 10000):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.trades = []
        self.holding_stock = None
        self._stock_names = None

    def calculate_commission(self, price: float, shares: int, is_sell: bool = False) -> Tuple[float, float]:
        turnover = float(price) * int(shares)
        commission = turnover * COMMISSION_RATE
        stamp_tax = turnover * STAMP_TAX_RATE if is_sell else 0
        commission = max(commission, 5)
        return commission, stamp_tax

    def execute_buy(self, price: float, shares: int) -> Dict:
        turnover = float(price) * int(shares)
        commission, _ = self.calculate_commission(price, shares, is_sell=False)
        total_cost = turnover + commission
        self.current_capital -= total_cost
        return {
            'type': 'buy',
            'price': price,
            'shares': shares,
            'turnover': turnover,
            'commission': commission,
            'cost': total_cost,
            'remaining_capital': self.current_capital
        }

    def execute_sell(self, price: float, shares: int) -> Dict:
        turnover = float(price) * int(shares)
        commission, stamp_tax = self.calculate_commission(price, shares, is_sell=True)
        total_proceeds = turnover - commission - stamp_tax
        self.current_capital += total_proceeds
        return {
            'type': 'sell',
            'price': price,
            'shares': shares,
            'turnover': turnover,
            'commission': commission,
            'stamp_tax': stamp_tax,
            'proceeds': total_proceeds,
            'remaining_capital': self.current_capital
        }

    def simulate_trade_on_historical_data(self, df: pd.DataFrame, current_date: pd.Timestamp) -> Optional[float]:
        """
        在历史数据上模拟交易以计算收益率（用于选股阶段）。
        回看一个月窗口，以最近一次金叉作为买入点，MACD下降作为卖出点。
        """
        df = df.reset_index(drop=True)
        window_end = current_date - pd.Timedelta(days=1)
        window_start = window_end - pd.Timedelta(days=90)

        mask = (df['trade_date'] >= window_start) & (df['trade_date'] <= window_end)
        trade_range = df[mask].copy()

        if len(trade_range) < 2:
            return None

        golden_cross_idx = None
        for i in range(len(trade_range) - 1, 0, -1):
            current = trade_range.iloc[i]
            prev = trade_range.iloc[i - 1]

            if (current['DIFF'] > 0 and
                current['DEA'] > 0 and
                is_golden_cross(current['DIFF'], current['DEA'],
                              prev['DIFF'], prev['DEA'])):
                golden_cross_idx = i
                break

        if golden_cross_idx is None:
            return None

        buy_price = float(trade_range.iloc[golden_cross_idx]['close_price'])

        for j in range(golden_cross_idx + 1, len(trade_range)):
            current = trade_range.iloc[j]
            prev = trade_range.iloc[j - 1]

            if pd.notna(current['MACD']) and pd.notna(prev['MACD']):
                if current['MACD'] < prev['MACD']:
                    sell_price = float(current['close_price'])
                    return_rate = (sell_price - buy_price) / buy_price
                    return return_rate

        return None

    def stock_has_golden_cross_on_date(self, df: pd.DataFrame, target_date: pd.Timestamp) -> bool:
        """检查股票在指定日期是否有金叉"""
        df = df.reset_index(drop=True)
        rows = df[df['trade_date'] == target_date]
        if len(rows) < 1:
            return False

        row_idx = rows.index[0]
        if row_idx == 0:
            return False

        current = df.iloc[row_idx]
        prev = df.iloc[row_idx - 1]

        return (current['DIFF'] > 0 and
                current['DEA'] > 0 and
                is_golden_cross(current['DIFF'], current['DEA'],
                              prev['DIFF'], prev['DEA']))

    def stock_price_on_date(self, df: pd.DataFrame, target_date: pd.Timestamp, price_type: str = 'close') -> Optional[float]:
        """获取指定日期的股价"""
        df = df.reset_index(drop=True)
        rows = df[df['trade_date'] == target_date]
        if len(rows) > 0:
            if price_type == 'open':
                return float(rows.iloc[0]['open_price'])
            return float(rows.iloc[0]['close_price'])
        return None

    def is_limit_up_on_prev_day(self, df: pd.DataFrame, target_date: pd.Timestamp) -> bool:
        """检查股票在前一交易日是否涨停"""
        df = df.reset_index(drop=True)
        rows = df[df['trade_date'] < target_date]
        if len(rows) < 1:
            return False
        prev_row = rows.iloc[-1]
        prev_prev_row = rows.iloc[-2] if len(rows) >= 2 else None

        if prev_prev_row is None:
            return False

        up_ratio = (float(prev_row['close_price']) - float(prev_prev_row['close_price'])) / float(prev_prev_row['close_price'])
        return up_ratio >= 0.099

    def is_macd_negative_prev_day(self, df: pd.DataFrame, target_date: pd.Timestamp) -> bool:
        """检查前一日MACD是否为负值（买入要求前一日MACD<0）"""
        df = df.reset_index(drop=True)
        rows = df[df['trade_date'] < target_date]
        if len(rows) < 1:
            return False  # 数据不足时放行，不跳过
        prev_row = rows.iloc[-1]
        if pd.isna(prev_row['MACD']):
            return False  # MACD数据缺失时放行，不跳过
        return prev_row['MACD'] >= 0

    def is_macd_too_small_last_5_days(self, df: pd.DataFrame, target_date: pd.Timestamp) -> bool:
        """检查前5个交易日MACD是否一直很小（接近零）"""
        df = df.reset_index(drop=True)
        rows = df[df['trade_date'] < target_date]
        if len(rows) < 5:
            return False

        last_5 = rows.tail(5)
        threshold = 0.05
        for _, row in last_5.iterrows():
            if pd.notna(row['MACD']) and abs(row['MACD']) >= threshold:
                return False
        return True

    def _get_stock_names(self) -> Dict[str, str]:
        """懒加载股票名称"""
        if self._stock_names is None:
            self._stock_names = get_all_stock_names()
        return self._stock_names

    def is_st_stock(self, stock_code: str) -> bool:
        """检查是否为ST股"""
        names = self._get_stock_names()
        name = names.get(stock_code, '')
        return 'ST' in name or 'st' in name or 'ST' in name.upper()

    def run_monthly_backtest(self, stock_data: Dict[str, pd.DataFrame],
                            start_date: str, end_date: str) -> Dict:
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)

        self.current_capital = self.initial_capital
        self.trades = []
        self.holding_stock = None

        current_date = start_dt
        trade_count = 0

        print(f"\n[{start_date} 至 {end_date}] 初始资金: {self.initial_capital:.2f}")

        while current_date <= end_dt:
            today_has_data = any(
                len(df[df['trade_date'] == current_date]) > 0
                for df in stock_data.values()
            )
            if not today_has_data:
                current_date += pd.Timedelta(days=1)
                continue

            if self.holding_stock:
                stock_code = self.holding_stock['code']
                df = self.holding_stock['df']
                buy_idx = self.holding_stock['buy_idx']

                today_idx = None
                for i in range(buy_idx + 1, len(df)):
                    if df.iloc[i]['trade_date'] == current_date:
                        today_idx = i
                        break

                if today_idx is not None and today_idx < len(df):
                    current_row = df.iloc[today_idx]
                    prev_row = df.iloc[today_idx - 1]

                    if (pd.notna(current_row['MACD']) and pd.notna(prev_row['MACD']) and
                        current_row['MACD'] < prev_row['MACD']):
                        sell_trade = self.execute_sell(current_row['close_price'], self.holding_stock['shares'])
                        sell_trade['stock_code'] = stock_code
                        sell_trade['date'] = current_row['trade_date']
                        self.trades.append(sell_trade)

                        buy_trade = self.trades[-2]
                        profit = sell_trade['proceeds'] - buy_trade['cost']
                        return_rate = (profit / buy_trade['cost']) * 100

                        print(f"\n[{current_row['trade_date'].date()}] 卖出 {stock_code}")
                        print(f"  收盘价: {current_row['close_price']:.2f}, 盈亏: {profit:.2f}, 收益率: {return_rate:.2f}%")
                        print(f"  当前资金: {self.current_capital:.2f}")

                        self.holding_stock = None

            if self.holding_stock is None and self.current_capital >= 1000 and current_date != end_dt:
                golden_cross_stocks = []

                for stock_code, df in stock_data.items():
                    if len(df) < 34:
                        continue
                    if not is_main_board_stock(stock_code):
                        continue

                    if self.stock_has_golden_cross_on_date(df, current_date):
                        golden_cross_stocks.append((stock_code, df))

                if golden_cross_stocks:
                    print(f"\n[{current_date.date()}] 选股: 发现 {len(golden_cross_stocks)} 只主板金叉股票, 正在进行历史回测...")

                candidates = []
                for stock_code, df in golden_cross_stocks:
                    sim_return = self.simulate_trade_on_historical_data(df, current_date)

                    if sim_return is not None:
                        candidates.append({
                            'stock_code': stock_code,
                            'df': df,
                            'sim_return': sim_return
                        })

                if candidates:
                    candidates.sort(key=lambda x: x['sim_return'], reverse=True)

                    best = None
                    for candidate in candidates:
                        cand_df = candidate['df'].reset_index(drop=True)

                        if self.is_macd_negative_prev_day(cand_df, current_date):
                            continue
                        if self.is_limit_up_on_prev_day(cand_df, current_date):
                            continue
                        if self.is_macd_too_small_last_5_days(cand_df, current_date):
                            continue
                        if self.is_st_stock(candidate['stock_code']):
                            continue

                        best = candidate
                        best_df = cand_df
                        break

                    if best is None:
                        current_date += pd.Timedelta(days=1)
                        continue

                    open_price = self.stock_price_on_date(best_df, current_date, price_type='open')
                    if open_price is None:
                        current_date += pd.Timedelta(days=1)
                        continue

                    shares = int(self.current_capital / open_price / 100) * 100

                    if shares >= 100:
                        buy_trade = self.execute_buy(open_price, shares)
                        buy_trade['stock_code'] = best['stock_code']
                        buy_trade['date'] = current_date
                        self.trades.append(buy_trade)

                        buy_idx_in_df = None
                        for i in range(len(best_df)):
                            if best_df.iloc[i]['trade_date'] == current_date:
                                buy_idx_in_df = i
                                break

                        self.holding_stock = {
                            'code': best['stock_code'],
                            'df': best_df,
                            'buy_price': open_price,
                            'shares': shares,
                            'buy_idx': buy_idx_in_df
                        }

                        print(f"\n[{current_date.date()}] 买入 {best['stock_code']}")
                        print(f"  历史模拟收益率: {best['sim_return']*100:.2f}%, 排名: 1/{len(candidates)}")
                        print(f"  开盘价: {open_price:.2f}, 股数: {shares}, 成本: {buy_trade['cost']:.2f}")
                        print(f"  剩余资金: {self.current_capital:.2f}")

                        trade_count += 1

            current_date += pd.Timedelta(days=1)

        if self.holding_stock:
            last_row = None
            df = self.holding_stock['df']
            for i in range(len(df) - 1, -1, -1):
                if df.iloc[i]['trade_date'] <= end_dt:
                    last_row = df.iloc[i]
                    break

            if last_row is not None:
                sell_trade = self.execute_sell(last_row['close_price'], self.holding_stock['shares'])
                sell_trade['stock_code'] = self.holding_stock['code']
                sell_trade['date'] = last_row['trade_date']
                self.trades.append(sell_trade)

                buy_trade = self.trades[-2]
                profit = sell_trade['proceeds'] - buy_trade['cost']
                return_rate = (profit / buy_trade['cost']) * 100

                print(f"\n[{last_row['trade_date'].date()}] 回测结束，强制卖出 {self.holding_stock['code']}")
                print(f"  收盘价: {last_row['close_price']:.2f}, 盈亏: {profit:.2f}, 收益率: {return_rate:.2f}%")
                print(f"  当前资金: {self.current_capital:.2f}")

        return self.generate_summary(trade_count, start_date, end_date)

    def generate_summary(self, trade_count: int, start_date: str, end_date: str) -> Dict:
        total_profit = self.current_capital - self.initial_capital
        total_return = (total_profit / self.initial_capital) * 100

        profits = []
        for i, trade in enumerate(self.trades):
            if trade['type'] == 'sell':
                buy_trade = self.trades[i - 1]
                profit = trade['proceeds'] - buy_trade['cost']
                profits.append(profit)

        winning_trades = len([p for p in profits if p > 0])
        losing_trades = len([p for p in profits if p <= 0])
        win_rate = (winning_trades / len(profits) * 100) if profits else 0
        avg_profit = (sum(profits) / len(profits)) if profits else 0

        summary = {
            'start_date': start_date,
            'end_date': end_date,
            'initial_capital': self.initial_capital,
            'final_capital': self.current_capital,
            'total_profit': total_profit,
            'total_return': total_return,
            'trade_count': trade_count,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'trades': self.trades
        }

        self.print_summary(summary)
        return summary

    def print_summary(self, summary: Dict):
        print("\n" + "="*70)
        print("月度回测汇总")
        print("="*70)
        print(f"回测周期: {summary['start_date']} 至 {summary['end_date']}")
        print("-"*70)
        print(f"初始资金: {summary['initial_capital']:.2f}")
        print(f"最终资金: {summary['final_capital']:.2f}")
        print(f"盈利金额: {summary['total_profit']:.2f}")
        print(f"总收益率: {summary['total_return']:.2f}%")
        print("-"*70)
        print(f"总交易次数: {summary['trade_count']}")
        print(f"盈利次数: {summary['winning_trades']}")
        print(f"亏损次数: {summary['losing_trades']}")
        print(f"胜率: {summary['win_rate']:.2f}%")
        print(f"每笔平均盈亏: {summary['avg_profit']:.2f}")
        print("="*70)

        if summary['trades']:
            print("\n[交易明细]")
            print("-"*70)
            print(f"{'#':<4} {'日期':<12} {'股票代码':<12} {'类型':<6} {'价格':<10} {'股数':<8} {'成交额':<12}")
            print("-"*70)

            for i, trade in enumerate(summary['trades'], 1):
                trade_date = trade['date'].date() if hasattr(trade['date'], 'date') else trade['date']
                print(f"{i:<4} {str(trade_date):<12} {trade['stock_code']:<12} "
                      f"{'买入' if trade['type'] == 'buy' else '卖出':<6} "
                      f"{trade['price']:<10.2f} {trade['shares']:<8} "
                      f"{trade['turnover']:<12.2f}")


def run_monthly_backtest(stock_data: Dict[str, pd.DataFrame],
                        start_date: str, end_date: str) -> Dict:
    backtest = MonthlyBacktest(initial_capital=10000)
    return backtest.run_monthly_backtest(stock_data, start_date, end_date)
