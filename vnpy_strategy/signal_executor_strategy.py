"""
信号执行策略 - VNPY CTA策略

接收外部选股器（external_stock_selector.py）输出的信号文件，
订阅对应股票，执行买入/卖出交易，并管理持仓。

架构：
    [PostgreSQL全市场扫描] --> [external_stock_selector.py] --> [signal.json]
                                                                          |
                                                                          v
                                                    [signal_executor_strategy.py]
                                                                          |
                                                                    订阅信号股票
                                                                    执行买卖

功能：
- 读取信号文件，获取目标股票和价格
- 自动订阅信号对应的股票（如需要可动态切换）
- 金叉日开盘价买入
- 持仓期间每日检查MACD下降信号，触发则卖出
- 超限持仓/止损时强制卖出
- 回写执行结果到信号文件

使用方法：
    1. 将本文件放入 VNPY strategies 文件夹
    2. 在CTA策略模块中添加策略实例
    3. 配置 signal_file 参数（指向 external_stock_selector.py 输出的 signal.json）
    4. 每天开盘前运行 external_stock_selector.py 生成信号
"""

from vnpy_ctastrategy import (
    CtaTemplate,
    StopOrder,
    BarData,
    TradeData,
    OrderData,
    ArrayManager,
)
from vnpy.trader.constant import Interval, Direction, Offset

import json
import os
import sys
from pathlib import Path

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Deque, Dict, Optional

import pandas as pd

# 动态添加依赖路径，确保能导入 macd_indicator 等模块
# __file__ 在 C:\Users\35223\strategies\signal_executor_strategy.py 时:
#   parent = C:\Users\35223\strategies
#   parent.parent = C:\Users\35223
_strategy_root = Path(__file__).parent.parent
_vnpy_strategy_path = _strategy_root / "MACD" / "vnpy_strategy"
if str(_vnpy_strategy_path) not in sys.path:
    sys.path.insert(0, str(_vnpy_strategy_path))

from macd_indicator import calculate_macd_on_series


# ============================================================
# 持仓信息
# ============================================================

@dataclass
class PositionInfo:
    symbol: str
    entry_price: float = 0.0
    shares: int = 0
    entry_bar_date: str = ""
    holding_bars: int = 0


# ============================================================
# 信号执行策略
# ============================================================

class SignalExecutorStrategy(CtaTemplate):
    """
    信号执行策略

    核心逻辑：
    1. 每根K线读取 signal.json
    2. 如果信号为buy且当前无持仓，订阅并买入信号股票
    3. 如果已有信号股票持仓，检查MACD下降信号并卖出
    4. 超限持仓/止损时强制卖出
    5. 将执行结果回写到信号文件
    """

    # ============ 策略参数 ============

    # 信号文件路径
    signal_file: str = "signal.json"

    # 交易参数
    fixed_shares: int = 100          # 固定股数（100的整数倍）
    stop_loss_pct: float = 0.0   # 止损比例（0表示不启用）
    max_holding_bars: int = 50   # 最大持仓K线数

    # MACD参数
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9

    # ============ 策略变量 ============

    diff: float = 0.0
    dea: float = 0.0
    macd: float = 0.0
    prev_diff: float = 0.0
    prev_dea: float = 0.0
    prev_macd: float = 0.0

    trade_count: int = 0
    winning_count: int = 0
    losing_count: int = 0
    total_pnl: float = 0.0

    current_signal: str = "none"   # 当前信号: "none" | "buy" | "sell"
    signal_symbol: str = ""        # 信号指向的股票
    signal_price: float = 0.0     # 信号参考价格
    signal_date: str = ""          # 信号日期

    author = "SignalExecutor"

    parameters = [
        "signal_file",
        "fixed_shares",
        "stop_loss_pct",
        "max_holding_bars",
        "fast_period",
        "slow_period",
        "signal_period",
    ]

    variables = [
        "diff", "dea", "macd",
        "prev_diff", "prev_dea", "prev_macd",
        "trade_count", "winning_count", "losing_count", "total_pnl",
        "current_signal", "signal_symbol", "signal_price",
    ]

    # =========================================================

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.am = ArrayManager()
        self._position: Optional[PositionInfo] = None
        self._signal_file = Path(self.signal_file)
        self._current_signal_data: Optional[dict] = None
        self._last_signal_mtime: float = 0.0

        self._close_buf: Deque[float] = deque(maxlen=self.slow_period * 3 + 10)
        self._macd_history: Deque[float] = deque(maxlen=10)
        self._last_bar_date: str = ""
        self._last_signal_date: str = ""  # 上次处理信号的日期（避免同一信号重复处理）

        self.write_log(f"信号执行策略初始化，信号文件: {self._signal_file}")

    def on_init(self):
        # 启动时自动检查 signal.json 中的股票代码是否与 vt_symbol 匹配
        signal_data = self._read_signal()
        if signal_data:
            signal_symbol = signal_data.get("symbol", "")
            if signal_symbol and signal_symbol != self.vt_symbol:
                self.write_log(
                    f"[警告] signal.json 中的股票({signal_symbol}) "
                    f"与配置的 vt_symbol({self.vt_symbol}) 不一致！"
                )
            elif signal_symbol:
                self.write_log(f"[信息] 自动识别信号股票: {signal_symbol}")
        else:
            self.write_log("[信息] signal.json 不存在或为空，将在每天开盘时自动读取")

        self.write_log("信号执行策略初始化，加载历史数据...")
        self.load_bar(60, Interval.DAILY)
        self.put_event()

    def _read_signal(self) -> Optional[dict]:
        """读取信号文件"""
        if not self._signal_file.exists():
            return None

        mtime = os.path.getmtime(self._signal_file)
        if mtime == self._last_signal_mtime:
            return self._current_signal_data

        self._last_signal_mtime = mtime

        try:
            with open(self._signal_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._current_signal_data = data
            return data
        except Exception:
            return None

    def _write_exec_result(self, result: dict):
        """将执行结果回写到信号文件"""
        if self._current_signal_data:
            self._current_signal_data['exec_result'] = result
            try:
                with open(self._signal_file, 'w', encoding='utf-8') as f:
                    json.dump(self._current_signal_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

    # --------------------------------------------------------
    # MACD计算（与external_stock_selector使用完全相同的逻辑）
    # --------------------------------------------------------

    def _compute_macd(self) -> tuple:
        closes = list(self._close_buf)
        need = self.slow_period + self.signal_period
        if len(closes) < need:
            return 0.0, 0.0, 0.0
        s = pd.Series(closes)
        diff_arr, dea_arr, macd_arr = calculate_macd_on_series(
            s,
            fast_period=self.fast_period,
            slow_period=self.slow_period,
            signal_period=self.signal_period
        )
        return float(diff_arr.iloc[-1]), float(dea_arr.iloc[-1]), float(macd_arr.iloc[-1])

    def _update_macd(self):
        if len(self._close_buf) < self.slow_period + self.signal_period:
            return
        diff, dea, macd = self._compute_macd()
        self.prev_diff = self.diff
        self.prev_dea = self.dea
        self.prev_macd = self.macd
        self.diff = diff
        self.dea = dea
        self.macd = macd
        self._macd_history.append(macd)

    # --------------------------------------------------------
    # 持仓管理
    # --------------------------------------------------------

    @property
    def has_position(self) -> bool:
        return self._position is not None and self._position.shares > 0

    def _is_macd_turning_down(self) -> bool:
        return (self.macd < self.prev_macd) and (self.prev_macd > 0)

    def _try_sell(self, bar_date: str, bar_close: float) -> bool:
        """
        检查是否需要卖出
        Returns: 是否触发了卖出
        """
        if not self.has_position:
            return False

        self._position.holding_bars += 1

        sell_reason = ""

        if self._is_macd_turning_down():
            sell_reason = "MACD下降"
        elif self._position.holding_bars >= self.max_holding_bars:
            sell_reason = f"超限({self.max_holding_bars}根K线)"
        elif self.stop_loss_pct > 0:
            if bar_close < self._position.entry_price * (1 - self.stop_loss_pct):
                sell_reason = f"止损({self.stop_loss_pct * 100:.1f}%)"

        if not sell_reason:
            return False

        self.sell(bar_close, self._position.shares)
        self._pending_sell_reason = sell_reason
        return True

    def _on_sell_filled(self, trade: TradeData):
        """卖出成交后的处理"""
        if not self._position:
            return

        pos = self._position
        sell_price = trade.price
        pnl = (sell_price - pos.entry_price) * pos.shares
        ret = (sell_price - pos.entry_price) / pos.entry_price * 100

        self.total_pnl += pnl
        self.trade_count += 1

        if pnl > 0:
            self.winning_count += 1
        else:
            self.losing_count += 1

        self.write_log(
            f"[卖出 {pos.symbol}] 原因:{self._pending_sell_reason} "
            f"价:{sell_price:.2f} 盈亏:{pnl:.2f} 收益率:{ret:.2f}%"
        )

        self._write_exec_result({
            "action": "sell",
            "symbol": pos.symbol,
            "price": sell_price,
            "shares": pos.shares,
            "pnl": pnl,
            "return_pct": ret,
            "holding_bars": pos.holding_bars,
            "sell_reason": self._pending_sell_reason,
        })

        self._position = None

    # --------------------------------------------------------
    # 信号处理
    # --------------------------------------------------------

    def _process_signal(self, bar_date: str, bar_close: float):
        """处理信号文件（每根K线调用一次）"""
        signal_data = self._read_signal()
        if signal_data is None:
            return

        signal = signal_data.get("signal", "none")
        symbol = signal_data.get("symbol", "")
        price = signal_data.get("price", 0.0)

        self.current_signal = signal
        self.signal_symbol = symbol
        self.signal_price = price
        self.signal_date = signal_data.get("date", "")

        # 同一信号、同一天不重复处理
        if signal_data.get("date") == self._last_signal_date and signal == self.current_signal:
            return

        self._last_signal_date = signal_data.get("date", "")

        # 有持仓时，检查是否需要卖出
        if self.has_position:
            if self._try_sell(bar_date, bar_close):
                return

        # 无持仓时，处理买入信号
        if not self.has_position and signal == "buy" and symbol:
            self._execute_buy(symbol, price, bar_date)

    def _execute_buy(self, symbol: str, price: float, bar_date: str):
        """执行买入"""
        if self.pos != 0:
            return

        shares = self.fixed_shares
        if shares < 100:
            return

        if price <= 0 and self.am.count > 0:
            price = self.am.close[-1]
        if price <= 0:
            return

        self.buy(price, shares)

        self._position = PositionInfo(
            symbol=symbol,
            entry_price=price,
            shares=shares,
            entry_bar_date=bar_date,
            holding_bars=0,
        )

        self._write_exec_result({
            "action": "buy",
            "symbol": symbol,
            "price": price,
            "shares": shares,
        })

        self.write_log(f"[买入 {symbol}] 价:{price:.2f} 量:{shares}")

    # --------------------------------------------------------
    # VNPY 回调函数
    # --------------------------------------------------------

    def on_start(self):
        self.write_log("信号执行策略启动")
        self.put_event()

    def on_stop(self):
        self.write_log("信号执行策略停止")
        self.cancel_all()
        self.put_event()

    def on_bar(self, bar: BarData):
        self._process_bar(bar)

    def _process_bar(self, bar: BarData):
        self.am.update_bar(bar)
        if not self.am.inited:
            self.put_event()
            return

        bar_date = bar.date.strftime("%Y-%m-%d") if hasattr(bar.date, 'strftime') else str(bar.date)

        if bar_date == self._last_bar_date:
            self.put_event()
            return
        self._last_bar_date = bar_date

        self._close_buf.append(bar.close_price)
        self._update_macd()

        self._process_signal(bar_date, bar.close_price)

        self.put_event()

    def on_order(self, order: OrderData):
        pass

    def on_trade(self, trade: TradeData):
        self.write_log(
            f"成交 {trade.vt_symbol}: dir={trade.direction.name} "
            f"price={trade.price:.2f} vol={trade.volume} "
            f"commission={trade.commission:.2f}"
        )
        # 卖出成交后处理
        if trade.direction == Direction.SHORT:
            self._on_sell_filled(trade)

    def on_stop_order(self, stop_order: StopOrder):
        pass
