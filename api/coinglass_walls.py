#!/usr/bin/env python3
"""
Coinglass Orderbook Walls Scraper
通过浏览器抓取大额挂单数据
"""

import subprocess
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple


def parse_wall_data(snapshot_text: str) -> Dict[str, Any]:
    """解析 Coinglass 挂单数据"""
    
    # 正则匹配挂单数据: "价格 $金额万 时间"
    pattern = r'(\d+(?:\.\d+)?)\s+\$(\d+(?:\.\d+)?)万\s+(\d+(?:天|小时|分钟|秒).*?)(?:\s+S|$)'
    
    walls = []
    for match in re.finditer(pattern, snapshot_text):
        price = float(match.group(1))
        amount_wan = float(match.group(2))  # 万为单位
        duration = match.group(3).strip()
        
        walls.append({
            "price": price,
            "amount_usd": amount_wan * 10000,  # 转为美元
            "amount_display": f"${amount_wan:.0f}万",
            "duration": duration
        })
    
    if not walls:
        return {"error": "No data parsed"}
    
    # 获取当前价格 (大约在中间)
    prices = [w["price"] for w in walls]
    current_price = sum(prices) / len(prices)  # 粗略估计
    
    # 分离买墙和卖墙
    bid_walls = sorted([w for w in walls if w["price"] < current_price], 
                       key=lambda x: x["price"], reverse=True)
    ask_walls = sorted([w for w in walls if w["price"] >= current_price],
                       key=lambda x: x["price"])
    
    # 计算总量
    total_bid = sum(w["amount_usd"] for w in bid_walls)
    total_ask = sum(w["amount_usd"] for w in ask_walls)
    
    # 找最厚的墙
    thickest_bid = max(bid_walls, key=lambda x: x["amount_usd"]) if bid_walls else None
    thickest_ask = max(ask_walls, key=lambda x: x["amount_usd"]) if ask_walls else None
    
    # 信号判断
    if total_bid > total_ask * 1.5:
        signal = "买墙厚实 (支撑强)"
        impact = "bullish"
    elif total_ask > total_bid * 1.5:
        signal = "卖墙厚实 (压力大)"
        impact = "bearish"
    else:
        signal = "挂单均衡"
        impact = "neutral"
    
    return {
        "timestamp": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "bid_walls": bid_walls[:10],
        "ask_walls": ask_walls[:10],
        "total_bid_usd": total_bid,
        "total_ask_usd": total_ask,
        "thickest_bid": thickest_bid,
        "thickest_ask": thickest_ask,
        "signal": signal,
        "impact": impact,
        "source": "coinglass"
    }


def format_walls_report(data: Dict) -> str:
    """格式化挂单报告"""
    if "error" in data:
        return f"Error: {data['error']}"
    
    lines = []
    lines.append("📊 Coinglass 大额挂单")
    lines.append("")
    
    lines.append("🔴 上方卖墙:")
    for w in data.get("ask_walls", [])[:5]:
        lines.append(f"  ${w['price']:,.0f} | {w['amount_display']} | {w['duration']}")
    
    lines.append("")
    lines.append("🟢 下方买墙:")
    for w in data.get("bid_walls", [])[:5]:
        lines.append(f"  ${w['price']:,.0f} | {w['amount_display']} | {w['duration']}")
    
    lines.append("")
    lines.append(f"买墙总量: ${data.get('total_bid_usd', 0)/1e6:.1f}M")
    lines.append(f"卖墙总量: ${data.get('total_ask_usd', 0)/1e6:.1f}M")
    lines.append(f"信号: {data.get('signal', 'N/A')}")
    
    return "\n".join(lines)


# 测试数据 (从截图解析)
TEST_DATA = """
72500 $275.55万 14小时 22分钟 S
72000 $1254.32万 6天 6小时 S
72000 $221.99万 2天 3小时 S
71900 $105.09万 2小时 35分钟 S
71666 $204.08万 15小时 24分钟 S
71500 $165.10万 18小时 26分钟 S
71360 $108.11万 5小时 8分钟 S
71300 $298.14万 14小时 8分钟 S
71000 $146.08万 4小时 4分钟 S
70750 $101.49万 20分钟 44秒 S
70699.9 $260.22万 26分钟 21秒 S
70225.25 $169.48万 1分钟 59秒 S
70035.1 $111.46万 0分钟 2秒 S
69635.7 $107.34万 0分钟 2秒 S
69418.53 $164.18万 2分钟 1秒 S
69300 $119.37万 2小时 6分钟 S
69000 $198.87万 17小时 8分钟 S
69000 $179.62万 16小时 38分钟 S
68500 $106.54万 14小时 30分钟 S
68000 $245.34万 1天 18小时 S
68000 $143.85万 1天 8小时 S
67500 $212.47万 2天 4小时 S
67000 $455.13万 2天 15小时 S
67000 $102.11万 4小时 47分钟 S
66500 $193.74万 1天 22小时 S
66000 $785.53万 3天 4小时 S
66000 $412.73万 2天 4小时
"""


if __name__ == "__main__":
    result = parse_wall_data(TEST_DATA)
    print(format_walls_report(result))
    print("\n" + "="*50 + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
