#!/usr/bin/env python3
"""
Price Trigger - 价格触发系统
到达关键位自动触发分析
"""

import requests
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

class PriceTrigger:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.base_url = "https://fapi.binance.com"
        self.state_file = os.path.join(os.path.dirname(__file__), "../data/trigger_state.json")
        
        # 关键价位配置 (从 MEMORY.md 的建仓区)
        self.trigger_zones = {
            "short_zone_1": {"min": 74000, "max": 75000, "direction": "short", "label": "第一压力区"},
            "short_zone_2": {"min": 78000, "max": 80000, "direction": "short", "label": "核心做空区"},
            "short_zone_3": {"min": 83000, "max": 85000, "direction": "short", "label": "极限做空区"},
            "long_zone_1": {"min": 62000, "max": 63000, "direction": "long", "label": "第一支撑区"},
            "long_zone_2": {"min": 58000, "max": 60000, "direction": "long", "label": "核心做多区"},
        }
        
        # 波动触发阈值
        self.volatility_threshold_pct = 3.0  # 日内波动 >3%
        
        # 冷却时间 (秒) - 同一区域触发后多久才能再次触发
        self.cooldown_seconds = 3600 * 4  # 4小时
    
    def get_price(self) -> float:
        """获取当前价格"""
        url = f"{self.base_url}/fapi/v1/ticker/price"
        params = {"symbol": self.symbol}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return float(data["price"])
        except:
            return 0
    
    def get_24h_stats(self) -> Dict[str, float]:
        """获取24H统计"""
        url = f"{self.base_url}/fapi/v1/ticker/24hr"
        params = {"symbol": self.symbol}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return {
                "high": float(data["highPrice"]),
                "low": float(data["lowPrice"]),
                "change_pct": float(data["priceChangePercent"]),
                "volume": float(data["volume"])
            }
        except:
            return {}
    
    def load_state(self) -> Dict:
        """加载状态"""
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except:
            return {"last_triggers": {}, "last_price": 0}
    
    def save_state(self, state: Dict):
        """保存状态"""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def check_zone_trigger(self, price: float, state: Dict) -> Optional[Dict]:
        """检查是否触发价格区域"""
        now = datetime.now(timezone.utc).timestamp()
        
        for zone_id, zone in self.trigger_zones.items():
            if zone["min"] <= price <= zone["max"]:
                # 检查冷却
                last_trigger = state.get("last_triggers", {}).get(zone_id, 0)
                if now - last_trigger > self.cooldown_seconds:
                    return {
                        "type": "zone",
                        "zone_id": zone_id,
                        "zone": zone,
                        "price": price,
                        "message": f"🎯 价格进入 {zone['label']} (${zone['min']:,}-${zone['max']:,})，方向: {zone['direction'].upper()}"
                    }
        return None
    
    def check_volatility_trigger(self, stats: Dict, state: Dict) -> Optional[Dict]:
        """检查波动率触发"""
        if not stats:
            return None
        
        change_pct = abs(stats.get("change_pct", 0))
        if change_pct >= self.volatility_threshold_pct:
            now = datetime.now(timezone.utc).timestamp()
            last_trigger = state.get("last_triggers", {}).get("volatility", 0)
            
            if now - last_trigger > self.cooldown_seconds:
                direction = "上涨" if stats["change_pct"] > 0 else "下跌"
                return {
                    "type": "volatility",
                    "change_pct": stats["change_pct"],
                    "message": f"📈 日内波动超过 {self.volatility_threshold_pct}%！当前 {direction} {abs(stats['change_pct']):.1f}%"
                }
        return None
    
    def check_breakout_trigger(self, price: float, stats: Dict, state: Dict) -> Optional[Dict]:
        """检查突破触发 (新高/新低)"""
        if not stats:
            return None
        
        now = datetime.now(timezone.utc).timestamp()
        last_trigger = state.get("last_triggers", {}).get("breakout", 0)
        
        if now - last_trigger < self.cooldown_seconds:
            return None
        
        high = stats.get("high", 0)
        low = stats.get("low", float("inf"))
        
        # 检查是否接近24H高/低点 (0.5%内)
        if price >= high * 0.995:
            return {
                "type": "breakout",
                "direction": "high",
                "message": f"🔺 接近24H高点 ${high:,.0f}，可能突破"
            }
        elif price <= low * 1.005:
            return {
                "type": "breakout",
                "direction": "low",
                "message": f"🔻 接近24H低点 ${low:,.0f}，可能跌破"
            }
        
        return None
    
    def check(self) -> Dict[str, Any]:
        """运行检查"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        price = self.get_price()
        stats = self.get_24h_stats()
        state = self.load_state()
        
        if not price:
            return {"error": "无法获取价格", "triggered": False}
        
        triggers = []
        
        # 检查各种触发条件
        zone_trigger = self.check_zone_trigger(price, state)
        if zone_trigger:
            triggers.append(zone_trigger)
            state.setdefault("last_triggers", {})[zone_trigger["zone_id"]] = datetime.now(timezone.utc).timestamp()
        
        volatility_trigger = self.check_volatility_trigger(stats, state)
        if volatility_trigger:
            triggers.append(volatility_trigger)
            state.setdefault("last_triggers", {})["volatility"] = datetime.now(timezone.utc).timestamp()
        
        breakout_trigger = self.check_breakout_trigger(price, stats, state)
        if breakout_trigger:
            triggers.append(breakout_trigger)
            state.setdefault("last_triggers", {})["breakout"] = datetime.now(timezone.utc).timestamp()
        
        # 更新状态
        state["last_price"] = price
        state["last_check"] = timestamp
        self.save_state(state)
        
        return {
            "timestamp": timestamp,
            "price": price,
            "stats": stats,
            "triggered": len(triggers) > 0,
            "triggers": triggers
        }
    
    def update_zones(self, zones: Dict[str, Dict]):
        """动态更新触发区域"""
        self.trigger_zones.update(zones)


def main():
    trigger = PriceTrigger("BTCUSDT")
    result = trigger.check()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
