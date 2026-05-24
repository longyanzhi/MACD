"""
全市场股票扫描 + 历史模拟 + 排序选优模块

对应 monthly_backtest.py 中的完整选股流程：
1. 扫描全市场股票，找到当天出现金叉的股票
2. 对每个候选股票，在过去 N 天窗口内模拟：金叉买入 → MACD下降卖出
3. 按历史模拟收益率排序
4. 逐个检查过滤条件（MACD<0、非涨停、非ST等），返回最优候选

用法：
    selector = StockSelector()
    selector.load_data()                          # 加载数据
    candidates = selector.scan(date)               # 扫描选股
    best = selector.pick_best(candidates)          # 过滤+选最优
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Deque, List, Optional

from macd_indicator import calculate_macd_on_series


def is_main_board(stock_code: str) -> bool:
    """判断是否为主板股票"""
    code = stock_code.replace(".SZ", "").replace(".SH", "")
    return (
        code.startswith("600") or code.startswith("601") or
        code.startswith("603") or code.startswith("605") or
        code.startswith("000") or code.startswith("001")
    )


@dataclass
class CandidateStock:
    """候选股票数据结构"""
    symbol: str            # 股票代码
    name: str              # 股票名称
    golden_cross_date: str  # 金叉日期
    golden_cross_price: float  # 金叉日收盘价

    # 历史模拟结果
    sim_buy_date: str = ""       # 模拟买入日期
    sim_buy_price: float = 0.0   # 模拟买入价格
    sim_sell_date: str = ""       # 模拟卖出日期
    sim_sell_price: float = 0.0  # 模拟卖出价格
    sim_return: float = 0.0       # 模拟收益率（%）

    # 过滤检查结果
    prev_macd_neg: bool = False  # 前一日MACD < 0
    not_limit_up: bool = False    # 前一日非涨停
    not_st: bool = False          # 非ST股
    macd_not_small: bool = False  # 前5日MACD非持续很小


class StockSelector:
    """
    全市场股票选股器
    实现与 monthly_backtest.py 完全一致的选股逻辑
    """

    def __init__(
        self,
        lookback_days: int = 90,
        macd_small_threshold: float = 0.05,
        limit_up_ratio: float = 0.099,
    ):
        self.lookback_days = lookback_days
        self.macd_small_threshold = macd_small_threshold
        self.limit_up_ratio = limit_up_ratio

        # 全市场股票数据: {symbol: [(date, open, high, low, close, vol), ...]}
        self._data: dict = {}
        self._names: dict = {}

    def load_data(self, data: dict, names: dict = None):
        """
        加载全市场股票数据

        Args:
            data: {symbol: DataFrame or list of (date,open,high,low,close,vol)}
            names: {symbol: name}
        """
        self._data = data
        self._names = names or {}

    def set_data(self, symbol: str, rows: List[tuple]):
        """
        设置单支股票数据（用于逐个添加数据）

        Args:
            symbol: 股票代码
            rows: [(date, open, high, low, close, vol), ...]，需按日期升序
        """
        self._data[symbol] = sorted(rows, key=lambda r: r[0])

    def set_name(self, symbol: str, name: str):
        self._names[symbol] = name

    # --------------------------------------------------------
    # 核心选股流程
    # --------------------------------------------------------

    def scan(self, date_str: str) -> List[CandidateStock]:
        """
        扫描全市场，找到指定日期出现金叉的股票

        Args:
            date_str: 扫描日期，格式 'YYYY-MM-DD'

        Returns:
            候选股票列表（含历史模拟收益率）
        """
        candidates = []

        for symbol, rows in self._data.items():
            candidate = self._check_single(symbol, rows, date_str)
            if candidate:
                candidates.append(candidate)

        candidates.sort(key=lambda c: c.sim_return, reverse=True)
        return candidates

    def pick_best(self, candidates: List[CandidateStock]) -> Optional[CandidateStock]:
        """
        从候选列表中选取最优股票
        按历史模拟收益率从高到低，逐个检查过滤条件，返回第一个满足全部条件的

        过滤条件：
        1. 前一日MACD < 0
        2. 前一日非涨停
        3. 非ST股
        4. 前5日MACD非持续很小

        Args:
            candidates: scan() 返回的候选列表

        Returns:
            最优候选股票，或None（无满足条件的股票）
        """
        for candidate in candidates:
            if self._passes_all_filters(candidate):
                return candidate
        return None

    # --------------------------------------------------------
    # 单股票金叉检查 + 历史模拟
    # --------------------------------------------------------

    def _check_single(self, symbol: str, rows: list, date_str: str) -> Optional[CandidateStock]:
        """
        检查单支股票是否在指定日期满足金叉条件，
        并做历史模拟（回看30天窗口内最近一次金叉买入→MACD下降卖出）

        Args:
            symbol: 股票代码
            rows: 该股票的所有历史数据，[(date, open, high, low, close, vol), ...]
            date_str: 检查日期

        Returns:
            CandidateStock 或 None
        """
        if len(rows) < 40:
            return None

        # 先检查主板（与回测逻辑一致：先主板过滤再计算MACD）
        if not is_main_board(symbol):
            return None

        # 找到指定日期在rows中的索引
        target_idx = None
        for i, row in enumerate(rows):
            if str(row[0]) == date_str or str(row[0])[:10] == date_str:
                target_idx = i
                break
        if target_idx is None or target_idx < 1:
            return None

        # 取指定日期及之前足够多的数据（用于计算MACD）
        start_idx = max(0, target_idx - 60)
        slice_rows = rows[start_idx:target_idx + 1]

        closes = [r[4] for r in slice_rows]
        diff_arr, dea_arr, macd_arr = calculate_macd_on_series(closes)

        cur_idx = len(slice_rows) - 1
        prev_idx = cur_idx - 1

        # 金叉条件: DIFF>0, DEA>0, DIFF上穿DEA
        diff = diff_arr[cur_idx]
        dea = dea_arr[cur_idx]
        prev_diff = diff_arr[prev_idx]
        prev_dea = dea_arr[prev_idx]

        if not (diff > dea and prev_diff <= prev_dea and diff > 0 and dea > 0):
            return None

        golden_date = slice_rows[cur_idx][0]
        golden_price = slice_rows[cur_idx][4]  # 收盘价

        # 历史模拟：在target_date之前的30天窗口内找最近一次金叉
        sim_result = self._simulate_history(slice_rows, diff_arr, dea_arr, macd_arr, cur_idx)

        candidate = CandidateStock(
            symbol=symbol,
            name=self._names.get(symbol, ""),
            golden_cross_date=str(golden_date),
            golden_cross_price=golden_price,
            sim_buy_date=sim_result["buy_date"],
            sim_buy_price=sim_result["buy_price"],
            sim_sell_date=sim_result["sell_date"],
            sim_sell_price=sim_result["sell_price"],
            sim_return=sim_result["return_pct"],
        )

        # 过滤条件检查
        candidate.prev_macd_neg = prev_idx >= 0 and macd_arr[prev_idx] < 0
        candidate.not_limit_up = self._check_not_limit_up(rows, start_idx + cur_idx)
        candidate.not_st = "ST" not in self._names.get(symbol, "").upper()
        candidate.macd_not_small = self._check_macd_not_small(macd_arr, prev_idx)

        return candidate

    def _simulate_history(
        self,
        slice_rows: list,
        diff_arr: list,
        dea_arr: list,
        macd_arr: list,
        cur_idx: int
    ) -> dict:
        """
        在当前日期之前的 lookback_days 天窗口内，
        找最近一次金叉，买入后等MACD下降卖出，计算收益率

        对应 monthly_backtest.py: simulate_trade_on_historical_data()
        """
        window_start = cur_idx - self.lookback_days
        if window_start < 1:
            window_start = 1

        golden_idx = None
        for i in range(cur_idx - 1, window_start - 1, -1):
            diff = diff_arr[i]
            dea = dea_arr[i]
            prev_diff = diff_arr[i - 1]
            prev_dea = dea_arr[i - 1]
            if diff > dea and prev_diff <= prev_dea and diff > 0 and dea > 0:
                golden_idx = i
                break

        if golden_idx is None:
            return {"buy_date": "", "buy_price": 0.0, "sell_date": "", "sell_price": 0.0, "return_pct": -999.0}

        buy_price = slice_rows[golden_idx][4]  # 收盘价买入

        sell_price = buy_price
        sell_date = ""
        for j in range(golden_idx + 1, cur_idx):
            cur_macd = macd_arr[j]
            prev_macd = macd_arr[j - 1]
            if cur_macd is not None and prev_macd is not None and cur_macd < prev_macd:
                sell_price = slice_rows[j][4]
                sell_date = str(slice_rows[j][0])
                break

        ret = (sell_price - buy_price) / buy_price * 100 if buy_price > 0 else -999.0
        return {
            "buy_date": str(slice_rows[golden_idx][0]),
            "buy_price": buy_price,
            "sell_date": sell_date,
            "sell_price": sell_price,
            "return_pct": ret,
        }

    def _check_not_limit_up(self, rows: list, target_idx: int) -> bool:
        """检查前一根K线是否涨停"""
        if target_idx < 2:
            return True
        prev = rows[target_idx - 1]
        prev_prev = rows[target_idx - 2]
        if prev_prev[4] == 0:
            return True
        up_ratio = (prev[4] - prev_prev[4]) / prev_prev[4]
        return up_ratio < self.limit_up_ratio

    def _check_macd_not_small(self, macd_arr: list, end_idx: int) -> bool:
        """检查前5日MACD是否非持续很小"""
        if end_idx < 5:
            return True
        threshold = self.macd_small_threshold
        for i in range(end_idx - 4, end_idx + 1):
            if abs(macd_arr[i]) >= threshold:
                return True
        return False

    # --------------------------------------------------------
    # 过滤检查
    # --------------------------------------------------------

    def _passes_all_filters(self, candidate: CandidateStock) -> bool:
        return (
            candidate.prev_macd_neg
            and candidate.not_limit_up
            and candidate.not_st
            and candidate.macd_not_small
            and is_main_board(candidate.symbol)
        )
