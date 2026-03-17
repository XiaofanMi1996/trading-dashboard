#!/usr/bin/env python3
"""
Hyperliquid 持仓监控
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

class HyperliquidMonitor:
    def __init__(self, address: str):
        self.address = address
        self.api_url = "https://api.hyperliquid.xyz/info"
    
    def get_perp_state(self) -> Dict[str, Any]:
        """获取永续合约账户状态"""
        try:
            resp = requests.post(self.api_url, json={
                "type": "clearinghouseState",
                "user": self.address
            }, timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_spot_state(self) -> Dict[str, Any]:
        """获取现货账户状态"""
        try:
            resp = requests.post(self.api_url, json={
                "type": "spotClearinghouseState",
                "user": self.address
            }, timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_open_orders(self) -> Dict[str, Any]:
        """获取未成交订单"""
        try:
            resp = requests.post(self.api_url, json={
                "type": "openOrders",
                "user": self.address
            }, timeout=10)
            return resp.json()
        except Exception as e:
            return {"error": str(e)}
    
    def get_user_fills(self, limit: int = 20) -> Dict[str, Any]:
        """获取最近成交"""
        try:
            resp = requests.post(self.api_url, json={
                "type": "userFills",
                "user": self.address
            }, timeout=10)
            data = resp.json()
            return data[:limit] if isinstance(data, list) else data
        except Exception as e:
            return {"error": str(e)}
    
    def analyze(self) -> Dict[str, Any]:
        """完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        perp = self.get_perp_state()
        spot = self.get_spot_state()
        orders = self.get_open_orders()
        
        # 解析现货余额
        spot_balances = {}
        if "balances" in spot:
            for b in spot["balances"]:
                if float(b.get("total", 0)) > 0:
                    spot_balances[b["coin"]] = float(b["total"])
        
        # 解析永续持仓
        perp_positions = []
        if "assetPositions" in perp:
            for p in perp["assetPositions"]:
                pos = p.get("position", {})
                if pos:
                    size = float(pos.get("szi", 0))
                    if size != 0:
                        perp_positions.append({
                            "coin": pos.get("coin", ""),
                            "size": size,
                            "entry_price": float(pos.get("entryPx", 0)),
                            "mark_price": float(pos.get("markPrice", 0)) if "markPrice" in pos else 0,
                            "unrealized_pnl": float(pos.get("unrealizedPnl", 0)),
                            "margin_used": float(pos.get("marginUsed", 0)),
                            "liquidation_price": float(pos.get("liquidationPx", 0)) if pos.get("liquidationPx") else None,
                            "leverage": float(pos.get("leverage", {}).get("value", 1)) if isinstance(pos.get("leverage"), dict) else 1
                        })
        
        # 账户汇总
        perp_value = float(perp.get("marginSummary", {}).get("accountValue", 0))
        spot_value = sum(spot_balances.values())
        total_value = perp_value + spot_value
        
        # 风险检查
        alerts = []
        margin_used = float(perp.get("marginSummary", {}).get("totalMarginUsed", 0))
        if perp_value > 0 and margin_used / perp_value > 0.8:
            alerts.append("⚠️ 保证金使用率 >80%，注意风险")
        
        for pos in perp_positions:
            if pos["liquidation_price"] and pos["mark_price"]:
                if pos["size"] > 0:  # Long
                    dist = (pos["mark_price"] - pos["liquidation_price"]) / pos["mark_price"] * 100
                else:  # Short
                    dist = (pos["liquidation_price"] - pos["mark_price"]) / pos["mark_price"] * 100
                if dist < 5:
                    alerts.append(f"🚨 {pos['coin']} 距离清算价 <5%!")
        
        return {
            "timestamp": timestamp,
            "address": self.address[:10] + "..." + self.address[-4:],
            "total_value": round(total_value, 2),
            "spot": {
                "value": round(spot_value, 2),
                "balances": spot_balances
            },
            "perp": {
                "value": round(perp_value, 2),
                "margin_used": round(margin_used, 2),
                "positions": perp_positions
            },
            "open_orders": orders if isinstance(orders, list) else [],
            "has_positions": len(perp_positions) > 0,
            "alerts": alerts
        }
    
    def format_report(self, data: Dict) -> str:
        """格式化报告"""
        lines = []
        lines.append(f"📊 Hyperliquid 账户 | {data['address']}")
        lines.append(f"⏰ {data['timestamp']}")
        lines.append("")
        lines.append(f"💰 总资产: ${data['total_value']:,.2f}")
        lines.append(f"  • Spot: ${data['spot']['value']:,.2f}")
        lines.append(f"  • Perp: ${data['perp']['value']:,.2f}")
        
        if data["perp"]["positions"]:
            lines.append("")
            lines.append("📈 持仓:")
            for pos in data["perp"]["positions"]:
                direction = "🟢 Long" if pos["size"] > 0 else "🔴 Short"
                pnl_emoji = "✅" if pos["unrealized_pnl"] >= 0 else "❌"
                lines.append(f"  {pos['coin']} {direction} {abs(pos['size']):.4f}")
                lines.append(f"    开仓: ${pos['entry_price']:,.2f}")
                lines.append(f"    PnL: {pnl_emoji} ${pos['unrealized_pnl']:,.2f}")
                if pos["liquidation_price"]:
                    lines.append(f"    清算: ${pos['liquidation_price']:,.2f}")
        else:
            lines.append("")
            lines.append("📈 持仓: 无")
        
        if data["open_orders"]:
            lines.append("")
            lines.append(f"📋 挂单: {len(data['open_orders'])} 个")
        
        if data["alerts"]:
            lines.append("")
            for alert in data["alerts"]:
                lines.append(alert)
        
        return "\n".join(lines)


def main():
    address = "0x756434af0362a3437c9b1fc26b5b090a3186377c"
    monitor = HyperliquidMonitor(address)
    data = monitor.analyze()
    print(monitor.format_report(data))
    print("\n" + "="*50 + "\n")
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
