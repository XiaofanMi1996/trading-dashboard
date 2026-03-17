#!/usr/bin/env python3
"""
Realtime Monitor - 实时盘面监控
- 每5分钟检查一次（通过 cron 调用）
- 价格变化 >1% 或状态变化时触发通知
- 追踪盘面性质变化
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(__file__))

from key_level_alert import KeyLevelAlert

class RealtimeMonitor:
    def __init__(self):
        self.base_dir = os.path.dirname(__file__)
        self.state_file = os.path.join(self.base_dir, "../data/market_state.json")
        self.alert = KeyLevelAlert()
        
    def load_state(self) -> Dict:
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except:
            return {
                "last_update": None,
                "price": 0,
                "current_zone": None,
                "market_nature": None,
                "nature_history": [],
                "zone_history": [],
                "alerts_sent": []
            }
    
    def save_state(self, state: Dict):
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def check_and_notify(self) -> Dict:
        """检查盘面状态，返回需要通知的内容"""
        state = self.load_state()
        framework = self.alert.load_framework()
        
        current_price = self.alert.get_price()
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        notifications = []
        
        # 1. 检查价格变化
        last_price = state.get("price", 0)
        if last_price > 0:
            price_change_pct = (current_price - last_price) / last_price * 100
            if abs(price_change_pct) >= 1.0:
                notifications.append({
                    "type": "price_change",
                    "message": f"📊 **价格变动** | BTC ${current_price:,.0f}\n"
                              f"变化：{price_change_pct:+.1f}% (从 ${last_price:,.0f})"
                })
        
        # 2. 检查是否进入/离开交易区间
        current_zone = self.alert.get_current_zone(current_price, framework)
        last_zone = state.get("current_zone")
        
        zone_changed = False
        if current_zone and not last_zone:
            # 进入区间
            zone_changed = True
            zone = current_zone["zone"]
            zone_type = current_zone["type"]
            
            # 获取完整分析
            verification = self.alert.get_agent_verification("short" if zone_type == "resistance" else "long")
            candle = self.alert.check_candle_confirmation({"price": current_price}, "short" if zone_type == "resistance" else "long")
            
            analysis = self.alert.analyze_zone_entry(
                current_price, zone, zone_type, 
                verification, candle, framework
            )
            
            notifications.append({
                "type": "zone_enter",
                "zone": zone["name"],
                "message": analysis
            })
            
            # 记录盘面性质
            nature = self.alert.judge_market_nature(
                verification, candle, zone_type, "middle"
            )
            state["market_nature"] = nature
            state["nature_history"].append({
                "time": timestamp,
                "nature": nature["type"],
                "price": current_price
            })
            
        elif not current_zone and last_zone:
            # 离开区间
            zone_changed = True
            direction = "上" if current_price > last_zone.get("range", [0, 0])[1] else "下"
            notifications.append({
                "type": "zone_exit",
                "message": f"📤 **离开{last_zone.get('name', '交易区间')}**\n"
                          f"方向：向{direction}突破\n"
                          f"当前价：${current_price:,.0f}"
            })
        
        # 3. 检查盘面性质变化（在区间内）
        if current_zone and not zone_changed:
            zone = current_zone["zone"]
            zone_type = current_zone["type"]
            
            verification = self.alert.get_agent_verification("short" if zone_type == "resistance" else "long")
            candle = self.alert.check_candle_confirmation({"price": current_price}, "short" if zone_type == "resistance" else "long")
            
            new_nature = self.alert.judge_market_nature(
                verification, candle, zone_type, "middle"
            )
            
            old_nature = state.get("market_nature", {})
            if new_nature["type"] != old_nature.get("type"):
                # 性质变化
                notifications.append({
                    "type": "nature_change",
                    "message": f"🔄 **盘面性质变化** | BTC ${current_price:,.0f}\n\n"
                              f"之前：{old_nature.get('description', 'N/A')}\n"
                              f"现在：{new_nature['description']}\n"
                              f"→ {new_nature['action_hint']}"
                })
                
                state["market_nature"] = new_nature
                state["nature_history"].append({
                    "time": timestamp,
                    "nature": new_nature["type"],
                    "price": current_price
                })
        
        # 更新状态
        state["last_update"] = timestamp
        state["price"] = current_price
        state["current_zone"] = current_zone["zone"] if current_zone else None
        
        # 记录通知历史
        for n in notifications:
            state["alerts_sent"].append({
                "time": timestamp,
                "type": n["type"]
            })
        
        # 只保留最近50条历史
        state["nature_history"] = state["nature_history"][-50:]
        state["zone_history"] = state["zone_history"][-50:]
        state["alerts_sent"] = state["alerts_sent"][-100:]
        
        self.save_state(state)
        
        return {
            "timestamp": timestamp,
            "price": current_price,
            "zone": current_zone["zone"]["name"] if current_zone else None,
            "notifications": notifications,
            "should_notify": len(notifications) > 0
        }


def main():
    monitor = RealtimeMonitor()
    result = monitor.check_and_notify()
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if result["should_notify"]:
        print("\n" + "="*50)
        for n in result["notifications"]:
            print(n["message"])
            print()


if __name__ == "__main__":
    main()
