#!/usr/bin/env python3
"""
Coinbase Premium - Coinbase 溢价指数
计算 Coinbase BTC/USD vs Binance BTC/USDT 价差
"""

import requests
from typing import Dict, Optional

def get_coinbase_premium() -> Dict:
    """
    获取 Coinbase 溢价
    返回:
    {
        "binance_price": float,
        "coinbase_price": float,
        "premium_pct": float,
        "signal": "bullish" | "bearish" | "neutral",
        "description": str
    }
    """
    result = {
        "binance_price": 0,
        "coinbase_price": 0,
        "premium_pct": 0,
        "signal": "neutral",
        "description": "无法获取数据"
    }
    
    try:
        # Binance BTC/USDT
        binance_resp = requests.get(
            "https://api.binance.com/api/v3/ticker/price",
            params={"symbol": "BTCUSDT"},
            timeout=5
        )
        binance_price = float(binance_resp.json()["price"])
        
        # Coinbase BTC/USD
        coinbase_resp = requests.get(
            "https://api.coinbase.com/v2/prices/BTC-USD/spot",
            timeout=5
        )
        coinbase_price = float(coinbase_resp.json()["data"]["amount"])
        
        # 计算溢价
        premium_pct = (coinbase_price - binance_price) / binance_price * 100
        
        result["binance_price"] = binance_price
        result["coinbase_price"] = coinbase_price
        result["premium_pct"] = round(premium_pct, 4)
        
        # 判断信号
        if premium_pct > 0.15:
            result["signal"] = "bullish"
            result["description"] = f"正溢价 {premium_pct:+.3f}%：美国资金流入，偏多"
        elif premium_pct > 0.05:
            result["signal"] = "slightly_bullish"
            result["description"] = f"轻微正溢价 {premium_pct:+.3f}%：美国买盘略强"
        elif premium_pct < -0.15:
            result["signal"] = "bearish"
            result["description"] = f"负溢价 {premium_pct:+.3f}%：美国资金流出，偏空"
        elif premium_pct < -0.05:
            result["signal"] = "slightly_bearish"
            result["description"] = f"轻微负溢价 {premium_pct:+.3f}%：美国卖盘略强"
        else:
            result["signal"] = "neutral"
            result["description"] = f"溢价 {premium_pct:+.3f}%：中性"
        
    except Exception as e:
        result["description"] = f"获取失败: {str(e)}"
    
    return result


def get_premium_emoji(signal: str) -> str:
    """获取信号对应的 emoji"""
    mapping = {
        "bullish": "🟢",
        "slightly_bullish": "🟢",
        "bearish": "🔴",
        "slightly_bearish": "🔴",
        "neutral": "⚪"
    }
    return mapping.get(signal, "⚪")


if __name__ == "__main__":
    result = get_coinbase_premium()
    emoji = get_premium_emoji(result["signal"])
    
    print(f"📊 Coinbase Premium")
    print(f"Binance: ${result['binance_price']:,.2f}")
    print(f"Coinbase: ${result['coinbase_price']:,.2f}")
    print(f"{emoji} {result['description']}")
