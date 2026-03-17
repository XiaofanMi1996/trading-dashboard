#!/usr/bin/env python3
"""
Orderbook Walls Analyzer - 大额挂单分析
数据源: Coinglass Large Orderbook Statistics (需浏览器抓取)
或 Binance 深度数据 (API)
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple

class OrderbookWallsAnalyzer:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.base_url = "https://fapi.binance.com"
        # 大单阈值 (美元)
        self.wall_threshold_usd = 500000  # $500K 以上算墙
        self.mega_wall_threshold_usd = 2000000  # $2M 以上算巨墙
    
    def get_deep_orderbook(self, limit: int = 500) -> Dict[str, Any]:
        """获取深度订单簿"""
        url = f"{self.base_url}/fapi/v1/depth"
        params = {"symbol": self.symbol, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return data
        except Exception as e:
            return {"error": str(e)}
    
    def get_current_price(self) -> float:
        """获取当前价格"""
        url = f"{self.base_url}/fapi/v1/ticker/price"
        params = {"symbol": self.symbol}
        try:
            resp = requests.get(url, params=params, timeout=10)
            return float(resp.json()["price"])
        except:
            return 0
    
    def analyze_walls(self, orderbook: Dict, current_price: float) -> Dict[str, Any]:
        """分析挂单墙"""
        if "error" in orderbook or not current_price:
            return {"error": "No data"}
        
        bids = [[float(p), float(q)] for p, q in orderbook.get("bids", [])]
        asks = [[float(p), float(q)] for p, q in orderbook.get("asks", [])]
        
        # 找大额挂单
        bid_walls = []
        ask_walls = []
        
        for price, qty in bids:
            value_usd = price * qty
            if value_usd >= self.wall_threshold_usd:
                bid_walls.append({
                    "price": price,
                    "qty_btc": round(qty, 2),
                    "value_usd": round(value_usd, 0),
                    "distance_pct": round((current_price - price) / current_price * 100, 2),
                    "is_mega": value_usd >= self.mega_wall_threshold_usd
                })
        
        for price, qty in asks:
            value_usd = price * qty
            if value_usd >= self.wall_threshold_usd:
                ask_walls.append({
                    "price": price,
                    "qty_btc": round(qty, 2),
                    "value_usd": round(value_usd, 0),
                    "distance_pct": round((price - current_price) / current_price * 100, 2),
                    "is_mega": value_usd >= self.mega_wall_threshold_usd
                })
        
        # 按价格排序
        bid_walls.sort(key=lambda x: x["price"], reverse=True)  # 买墙从高到低
        ask_walls.sort(key=lambda x: x["price"])  # 卖墙从低到高
        
        # 计算总挂单量
        total_bid_usd = sum(w["value_usd"] for w in bid_walls)
        total_ask_usd = sum(w["value_usd"] for w in ask_walls)
        
        # 找最近的墙
        nearest_bid = bid_walls[0] if bid_walls else None
        nearest_ask = ask_walls[0] if ask_walls else None
        
        # 找最厚的墙
        thickest_bid = max(bid_walls, key=lambda x: x["value_usd"]) if bid_walls else None
        thickest_ask = max(ask_walls, key=lambda x: x["value_usd"]) if ask_walls else None
        
        # 信号判断
        wall_ratio = total_bid_usd / total_ask_usd if total_ask_usd else 1
        
        if wall_ratio > 1.5:
            signal = "买墙厚实 (支撑强)"
            impact = "bullish"
        elif wall_ratio < 0.67:
            signal = "卖墙厚实 (压力大)"
            impact = "bearish"
        else:
            signal = "挂单均衡"
            impact = "neutral"
        
        return {
            "current_price": current_price,
            "bid_walls": bid_walls[:10],  # 最多返回10个
            "ask_walls": ask_walls[:10],
            "nearest_bid": nearest_bid,
            "nearest_ask": nearest_ask,
            "thickest_bid": thickest_bid,
            "thickest_ask": thickest_ask,
            "total_bid_usd": total_bid_usd,
            "total_ask_usd": total_ask_usd,
            "wall_ratio": round(wall_ratio, 2),
            "signal": signal,
            "impact": impact
        }
    
    def format_walls_report(self, analysis: Dict) -> str:
        """格式化挂单墙报告"""
        if "error" in analysis:
            return f"Error: {analysis['error']}"
        
        lines = []
        lines.append(f"📊 大额挂单分析 | ${analysis['current_price']:,.0f}")
        lines.append("")
        
        # 卖墙 (上方压力)
        lines.append("🔴 上方卖墙:")
        if analysis["ask_walls"]:
            for w in analysis["ask_walls"][:5]:
                mega = "🔥" if w["is_mega"] else ""
                lines.append(f"  ${w['price']:,.0f} | {w['qty_btc']:.1f} BTC | ${w['value_usd']/1e6:.2f}M {mega}")
        else:
            lines.append("  无大额卖单")
        
        lines.append("")
        
        # 买墙 (下方支撑)
        lines.append("🟢 下方买墙:")
        if analysis["bid_walls"]:
            for w in analysis["bid_walls"][:5]:
                mega = "🔥" if w["is_mega"] else ""
                lines.append(f"  ${w['price']:,.0f} | {w['qty_btc']:.1f} BTC | ${w['value_usd']/1e6:.2f}M {mega}")
        else:
            lines.append("  无大额买单")
        
        lines.append("")
        lines.append(f"买/卖比: {analysis['wall_ratio']:.2f}")
        lines.append(f"信号: {analysis['signal']}")
        
        return "\n".join(lines)
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        current_price = self.get_current_price()
        orderbook = self.get_deep_orderbook(500)
        walls = self.analyze_walls(orderbook, current_price)
        
        return {
            "agent": "orderbook_walls",
            "timestamp": timestamp,
            "symbol": self.symbol,
            **walls
        }


def main():
    analyzer = OrderbookWallsAnalyzer("BTCUSDT")
    result = analyzer.analyze()
    
    print(analyzer.format_walls_report(result))
    print("\n" + "="*50 + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
