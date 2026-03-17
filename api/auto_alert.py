#!/usr/bin/env python3
"""
Auto Alert - 自动喊单系统
满足条件时自动推送分析
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from trading_desk import TradingDesk
from price_trigger import PriceTrigger
from signal_tracker import record_signal, check_open_signals, get_stats_summary


class AutoAlert:
    def __init__(self):
        self.desk = TradingDesk("BTCUSDT")
        self.price_trigger = PriceTrigger("BTCUSDT")
        self.state_file = os.path.join(os.path.dirname(__file__), "../data/alert_state.json")
        
        # 喊单阈值
        self.score_threshold = 4.0  # 评分 ≥4 或 ≤-4 才喊
        self.funding_extreme_high = 0.05  # 资金费率极端高
        self.funding_extreme_low = -0.03  # 资金费率极端低
        self.oi_change_threshold = 5.0  # OI 单小时变化 >5%
        
        # 冷却时间
        self.cooldown_minutes = 60  # 同类型信号60分钟内不重复喊
    
    def load_state(self) -> Dict:
        """加载状态"""
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except:
            return {"last_alerts": {}}
    
    def save_state(self, state: Dict):
        """保存状态"""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def check_cooldown(self, alert_type: str, state: Dict) -> bool:
        """检查冷却时间"""
        last_time = state.get("last_alerts", {}).get(alert_type, 0)
        now = datetime.now(timezone.utc).timestamp()
        return (now - last_time) > (self.cooldown_minutes * 60)
    
    def check_score_trigger(self, synthesis: Dict) -> Optional[Dict]:
        """检查评分触发"""
        score_data = synthesis.get("signal_score", {})
        score = score_data.get("final_score", 0)
        has_divergence = score_data.get("has_divergence", True)
        
        # 评分够且无分歧
        if abs(score) >= self.score_threshold and not has_divergence:
            direction = "多" if score > 0 else "空"
            
            # 获取技术面数据做过滤
            raw = synthesis.get("raw_analyses", {})
            tech = raw.get("technical", {})
            rsi_data = tech.get("rsi", {})
            boll_data = tech.get("bollinger", {})
            raw_data = tech.get("raw", {})
            
            # RSI 值 (取 1H 或 4H) - 直接是数值
            rsi_1h = rsi_data.get("1h", 50) if isinstance(rsi_data, dict) else 50
            rsi_4h = rsi_data.get("4h", 50) if isinstance(rsi_data, dict) else 50
            
            # 布林带位置 - 从 raw 里取各周期数据
            raw_1h = raw_data.get("1h", {})
            raw_4h = raw_data.get("4h", {})
            boll_1h = raw_1h.get("bollinger", {}).get("position", 50) if isinstance(raw_1h, dict) else 50
            boll_4h = raw_4h.get("bollinger", {}).get("position", 50) if isinstance(raw_4h, dict) else 50
            
            # 量价关系
            vol_1h = raw_1h.get("volume", {}).get("signal", "") if isinstance(raw_1h, dict) else ""
            
            # 过滤条件：不追高/不追低
            if score > 0:  # 做多信号
                # RSI 超买 (>70) 不喊多
                if rsi_1h > 70 or rsi_4h > 68:
                    return None
                # 破布林上轨 + 量缩 不喊多
                if boll_1h > 95 and "缩量" in vol_1h:
                    return None
                # 破布林上轨太多 不喊多
                if boll_1h > 110 or boll_4h > 105:
                    return None
            else:  # 做空信号
                # RSI 超卖 (<30) 不喊空
                if rsi_1h < 30 or rsi_4h < 32:
                    return None
                # 破布林下轨 + 量缩 不喊空
                if boll_1h < 5 and "缩量" in vol_1h:
                    return None
                # 破布林下轨太多 不喊空
                if boll_1h < -10 or boll_4h < -5:
                    return None
            
            return {
                "type": "score",
                "score": score,
                "direction": direction,
                "message": f"📊 信号评分 {score:+.1f} 触发做{direction}条件"
            }
        return None
    
    def check_funding_trigger(self, raw_analyses: Dict) -> Optional[Dict]:
        """检查资金费率触发"""
        deriv = raw_analyses.get("derivatives", {})
        funding = deriv.get("funding", {})
        rate = funding.get("current", 0) / 100  # 转为小数
        
        if rate >= self.funding_extreme_high:
            return {
                "type": "funding_high",
                "rate": rate * 100,
                "message": f"⚠️ 资金费率极高 {rate*100:.3f}%，做多成本高"
            }
        elif rate <= self.funding_extreme_low:
            return {
                "type": "funding_low",
                "rate": rate * 100,
                "message": f"🔔 资金费率极低 {rate*100:.3f}%，空头在付费"
            }
        return None
    
    def check_oi_trigger(self, raw_analyses: Dict) -> Optional[Dict]:
        """检查 OI 异动触发"""
        deriv = raw_analyses.get("derivatives", {})
        oi = deriv.get("open_interest", {}).get("history", {})
        change_4h = abs(oi.get("change_4h_pct", 0))
        
        if change_4h >= self.oi_change_threshold:
            direction = "增加" if oi.get("change_4h_pct", 0) > 0 else "减少"
            return {
                "type": "oi_spike",
                "change": oi.get("change_4h_pct", 0),
                "message": f"⚠️ OI 4H {direction} {change_4h:.1f}%，杠杆异动"
            }
        return None
    
    def check_price_zone_trigger(self) -> Optional[Dict]:
        """检查价格区域触发"""
        result = self.price_trigger.check()
        if result.get("triggered") and result.get("triggers"):
            trigger = result["triggers"][0]
            return {
                "type": "price_zone",
                "zone": trigger.get("zone_id", ""),
                "message": trigger.get("message", "价格进入关键区域")
            }
        return None
    
    def run(self) -> Dict[str, Any]:
        """运行检查"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        state = self.load_state()
        
        # 运行完整分析
        analyses = self.desk.run_all_analysts()
        synthesis = self.desk.synthesize(analyses)
        
        # 检查开放信号是否触发
        current_price = synthesis.get("price", 0)
        triggered_signals = check_open_signals(current_price) if current_price > 0 else []
        
        # 检查各种触发条件
        alerts = []
        
        # 1. 评分触发
        score_alert = self.check_score_trigger(synthesis)
        if score_alert and self.check_cooldown("score", state):
            alerts.append(score_alert)
            state.setdefault("last_alerts", {})["score"] = datetime.now(timezone.utc).timestamp()
        
        # 2. 资金费率触发
        funding_alert = self.check_funding_trigger(synthesis.get("raw_analyses", {}))
        if funding_alert and self.check_cooldown(funding_alert["type"], state):
            alerts.append(funding_alert)
            state.setdefault("last_alerts", {})[funding_alert["type"]] = datetime.now(timezone.utc).timestamp()
        
        # 3. OI 异动触发
        oi_alert = self.check_oi_trigger(synthesis.get("raw_analyses", {}))
        if oi_alert and self.check_cooldown("oi_spike", state):
            alerts.append(oi_alert)
            state.setdefault("last_alerts", {})["oi_spike"] = datetime.now(timezone.utc).timestamp()
        
        # 4. 价格区域触发
        price_alert = self.check_price_zone_trigger()
        if price_alert and self.check_cooldown(price_alert.get("zone", "price"), state):
            alerts.append(price_alert)
            state.setdefault("last_alerts", {})[price_alert.get("zone", "price")] = datetime.now(timezone.utc).timestamp()
        
        # 保存状态
        self.save_state(state)
        
        # 返回结果
        should_alert = len(alerts) > 0
        
        result = {
            "timestamp": timestamp,
            "should_alert": should_alert,
            "alerts": alerts,
            "synthesis": synthesis if should_alert else None,
            "price": synthesis.get("price", 0),
            "score": synthesis.get("signal_score", {}).get("final_score", 0)
        }
        
        # 加入触发的历史信号
        if triggered_signals:
            result["triggered_signals"] = triggered_signals
            for ts in triggered_signals:
                sig_alert = {
                    "type": "signal_triggered",
                    "signal_id": ts["signal"]["id"],
                    "result": ts["result"],
                    "pnl": ts["pnl_percent"],
                    "message": f"📌 信号 {ts['signal']['id']} {ts['status']} @ ${ts['closed_price']:,.0f} ({ts['pnl_percent']:+.1f}%)"
                }
                alerts.append(sig_alert)
                result["should_alert"] = True
        
        return result
    
    def format_alert_message(self, result: Dict) -> str:
        """格式化喊单消息"""
        if not result.get("should_alert"):
            return ""
        
        lines = []
        lines.append("🚨 **自动喊单触发**")
        lines.append("")
        lines.append(f"💵 价格: ${result['price']:,.0f}")
        lines.append(f"📊 评分: {result['score']:+.1f}")
        lines.append("")
        
        for alert in result.get("alerts", []):
            lines.append(f"• {alert['message']}")
        
        lines.append("")
        lines.append("正在生成完整分析...")
        
        return "\n".join(lines)


def main():
    alert = AutoAlert()
    result = alert.run()
    
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    
    if result["should_alert"]:
        print("\n" + "="*50)
        print(alert.format_alert_message(result))


if __name__ == "__main__":
    main()
