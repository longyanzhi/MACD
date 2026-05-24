# MACD金叉策略 - VNPY版本

本目录包含适配 VNPY CTA策略模块的 MACD 金叉交易策略，与上层回测系统逻辑完全一致。

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│  external_stock_selector.py（外部选股器，独立运行）           │
│  - 从PostgreSQL扫描全市场所有股票                          │
│  - 历史模拟30天窗口金叉收益排序                             │
│  - 输出最优候选到 signal.json                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ signal.json
┌─────────────────────────────────────────────────────────────┐
│  signal_executor_strategy.py（VNPY CTA策略）                │
│  - 读取signal.json                                        │
│  - 订阅信号股票，监控K线数据                               │
│  - 金叉日买入 → MACD下降/超限/止损卖出                     │
└─────────────────────────────────────────────────────────────┘
```

**完全保留原始回测逻辑**：全市场扫描 + 历史模拟排序 + 多重过滤，由外部选股器实现；VNPY策略只负责执行交易和管理持仓。

## 文件说明

```
vnpy_strategy/
├── external_stock_selector.py    # 外部全市场选股器（独立Python脚本）
├── signal_executor_strategy.py  # VNPY信号执行策略
├── macd_indicator.py           # MACD指标计算工具
├── stock_selector.py           # 选股器核心类（被外部选股器调用）
└── README.md                   # 本文件
```

## 快速开始

### 步骤1：安装依赖

确保安装了VNPY和相关依赖：

```bash
pip install vnpy
```

### 步骤2：配置数据库

在 `MACD_Stock_Strategy/config.py` 中配置PostgreSQL数据库连接。

### 步骤3：运行选股器（每天开盘前）

```bash
cd MACD_Stock_Strategy
python vnpy_strategy/external_stock_selector.py --date 2025-01-15
```

或使用今天日期（默认）：

```bash
python vnpy_strategy/external_stock_selector.py
```

选股器将：
1. 连接PostgreSQL，扫描全市场所有股票
2. 对每只股票计算MACD，找到金叉候选
3. 对候选做30天历史模拟，计算收益率
4. 排序后输出最优候选到 `signal.json`

示例输出 `signal.json`：

```json
{
  "date": "2025-01-15",
  "signal": "buy",
  "symbol": "600000.SH",
  "name": "浦发银行",
  "price": 12.50,
  "sim_return": 8.50,
  "reason": "golden_cross_with_history_sim",
  "timestamp": "2025-01-15T08:30:00"
}
```

如果没有满足条件的股票：

```json
{
  "date": "2025-01-15",
  "signal": "none",
  "symbol": "",
  "price": 0.0,
  "reason": "no_candidates"
}
```

### 步骤4：配置VNPY策略

1. 将 `signal_executor_strategy.py` 放入VNPY的 `strategies` 文件夹
2. 在VNPY CTA策略模块中添加策略实例
3. 配置参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `signal_file` | `signal.json` | 信号文件路径 |
| `fixed_shares` | `100` | 固定股数（100的整数倍） |
| `stop_loss_pct` | `0.0` | 止损比例（0表示不启用） |
| `max_holding_bars` | `50` | 最大持仓K线数 |
| `fast_period` | `12` | MACD快速EMA周期 |
| `slow_period` | `26` | MACD慢速EMA周期 |
| `signal_period` | `9` | MACD Signal线周期 |

4. 将 `vt_symbol` 配置为信号文件中的股票代码（如 `600000.SH`）

### 步骤5：启动VNPY

启动VNPY VeighNa Trader，加载CTA策略模块，启动策略实例。

## 定时自动选股（Windows）

使用Windows任务计划程序，每天开盘前自动运行选股器：

1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：每天 08:30（开盘前30分钟）
4. 操作：启动程序
5. 程序：`python`，参数：`path\to\external_stock_selector.py`

## 定时自动选股（Linux/Mac）

```bash
crontab -e
# 添加以下行：
30 8 * * 1-5 cd /path/to/MACD_Stock_Strategy && python vnpy_strategy/external_stock_selector.py
```

## 信号说明

`signal.json` 的字段：

| 字段 | 说明 |
|------|------|
| `date` | 信号日期 |
| `signal` | 信号类型：`buy`/`none`/`sell`/`error` |
| `symbol` | 股票代码 |
| `name` | 股票名称 |
| `price` | 参考价格（信号日的收盘价/开盘价） |
| `sim_return` | 历史模拟收益率（%） |
| `reason` | 信号原因 |
| `timestamp` | 信号生成时间 |
| `exec_result` | VNPY执行结果（由策略回写） |

## 选股逻辑（对应 monthly_backtest.py）

```
1. 扫描全市场 → 找所有金叉股票（DIFF>0, DEA>0, DIFF上穿DEA）
2. 主板过滤 → 排除科创板(688)、创业板(002/003)
3. 历史模拟 → 每个候选在30天窗口内模拟：金叉买入→MACD下降卖出
4. 排序 → 按模拟收益率从高到低
5. 过滤 → 逐个检查：前一日MACD<0、非涨停、非ST、前5日MACD非持续很小
6. 输出 → 第一个通过全部过滤的股票作为最优候选
```

## VNPY策略交易逻辑

```
买入：信号为buy且当前无持仓 → 以信号价格买入
持有：每日检查MACD下降信号
卖出（满足任一）：
  1. MACD柱开始下降（当天MACD < 前一天MACD）
  2. 持仓K线数达到上限
  3. 触发止损比例
卖出后：等待下一个信号
```

## 注意事项

1. **开盘前运行选股**：建议在每天 08:30-09:00 运行 `external_stock_selector.py`，信号文件在当天有效
2. **信号过期**：策略通过文件修改时间判断信号是否更新，同一信号不会重复处理
3. **持仓跨日**：如果持仓触发MACD下降卖出后，仍持有上一个交易日信号指定的股票，策略不会重复买入同一只股票
4. **多标的订阅**：策略只订阅配置时的 `vt_symbol`，需要确保数据源有该标的的K线数据
