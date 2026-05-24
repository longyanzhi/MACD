"""
每日股票扫描并发送微信通知脚本
在 GitHub Actions 上定时运行，北京时间每天早上 9:00
"""

import sys
import os
import http.client
import urllib.parse
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from realtime_scanner import scan_today_signals, get_last_trading_day, log


def send_to_wechat(title: str, content: str, token: str) -> bool:
    """
    通过 pushplus 发送消息到微信

    Args:
        title: 消息标题
        content: 消息内容（支持HTML）
        token: pushplus token

    Returns:
        bool: 是否发送成功
    """
    try:
        conn = http.client.HTTPSConnection("www.pushplus.plus")

        # 构建查询参数
        params = {
            'token': token,
            'title': title,
            'content': content,
            'template': 'html',
            'channel': 'wechat'
        }

        query_string = urllib.parse.urlencode(params)
        url = f"/send?{query_string}"

        conn.request("GET", url)
        res = conn.getresponse()
        data = res.read().decode("utf-8")

        log(f"微信发送结果: {data}")
        return True
    except Exception as e:
        log(f"微信发送失败: {e}")
        return False


def format_signals_to_html(signals: list) -> str:
    """
    将信号列表格式化为 HTML 内容

    Args:
        signals: 信号列表

    Returns:
        str: HTML 格式的内容
    """
    if not signals:
        return "<p>今日未发现金叉信号</p>"

    html = "<table border='1' cellpadding='5' cellspacing='0' style='border-collapse:collapse;'>"
    html += "<tr style='background-color:#f0f0f0;'>"
    html += "<th>排名</th><th>股票代码</th><th>收盘价</th><th>DIFF</th><th>DEA</th><th>MACD</th><th>预期收益</th>"
    html += "</tr>"

    for i, sig in enumerate(signals[:10], 1):  # 只显示前10个
        ret_str = f"{sig['sim_return']:.2f}%" if sig['sim_return'] is not None else "N/A"
        html += f"<tr>"
        html += f"<td>{i}</td>"
        html += f"<td><b>{sig['stock_code']}</b></td>"
        html += f"<td>{sig['close_price']:.2f}</td>"
        html += f"<td>{sig['diff']:.4f}</td>"
        html += f"<td>{sig['dea']:.4f}</td>"
        html += f"<td>{sig['macd']:.4f}</td>"
        html += f"<td style='color:green;'><b>{ret_str}</b></td>"
        html += f"</tr>"

    html += "</table>"
    return html


def main():
    # 从环境变量获取 pushplus token
    token = os.environ.get('PUSHPLUS_TOKEN')
    if not token:
        log("错误: 未设置 PUSHPLUS_TOKEN 环境变量")
        sys.exit(1)

    log("=" * 60)
    log("开始每日股票扫描")
    log("=" * 60)

    # 获取最后一个交易日
    target_date = get_last_trading_day()
    log(f"扫描日期: {target_date}")

    # 运行扫描
    try:
        signals = scan_today_signals(target_date)
        log(f"发现 {len(signals)} 个金叉信号")
    except Exception as e:
        log(f"扫描失败: {e}")
        title = "❌ MACD 选股失败"
        content = f"<p>扫描过程出错: {str(e)}</p>"
        send_to_wechat(title, content, token)
        sys.exit(1)

    # 格式化内容
    html_content = format_signals_to_html(signals)

    # 构建标题
    signal_count = len(signals)
    if signal_count == 0:
        title = f"📊 MACD 选股 - {target_date} (无信号)"
    else:
        title = f"📊 MACD 选股 - {target_date} (发现 {signal_count} 个信号)"

    # 发送微信
    log(f"发送微信通知...")
    success = send_to_wechat(title, html_content, token)

    if success:
        log("✓ 微信通知发送成功")
    else:
        log("✗ 微信通知发送失败")
        sys.exit(1)

    log("=" * 60)
    log("完成")
    log("=" * 60)


if __name__ == "__main__":
    main()
