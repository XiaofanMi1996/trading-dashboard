#!/usr/bin/env python3
"""
Macro Analyst - 宏观分析脚本
数据源: 免费 API
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

class MacroAnalyst:
    def __init__(self):
        pass
    
    def get_fear_greed(self) -> Dict[str, Any]:
        """获取恐惧贪婪指数"""
        url = "https://api.alternative.me/fng/?limit=7"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if "data" in data and data["data"]:
                current = data["data"][0]
                history = [int(d["value"]) for d in data["data"]]
                
                value = int(current["value"])
                classification = current["value_classification"]
                
                # 趋势
                if len(history) >= 3:
                    if history[0] > history[2]:
                        trend = "上升"
                    elif history[0] < history[2]:
                        trend = "下降"
                    else:
                        trend = "持平"
                else:
                    trend = "未知"
                
                # 信号 (逆向指标)
                if value <= 20:
                    signal = "极度恐慌 (逆向看多)"
                    impact = "bullish"
                elif value <= 35:
                    signal = "恐慌 (偏多)"
                    impact = "bullish"
                elif value <= 55:
                    signal = "中性"
                    impact = "neutral"
                elif value <= 75:
                    signal = "贪婪 (偏空)"
                    impact = "bearish"
                else:
                    signal = "极度贪婪 (逆向看空)"
                    impact = "bearish"
                
                return {
                    "value": value,
                    "classification": classification,
                    "trend": trend,
                    "signal": signal,
                    "impact": impact,
                    "history_7d": history
                }
        except Exception as e:
            return {"error": str(e)}
        
        return {"error": "No data"}
    
    def get_btc_dominance(self) -> Dict[str, Any]:
        """获取 BTC 市值占比"""
        url = "https://api.coingecko.com/api/v3/global"
        try:
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if "data" in data:
                btc_dom = data["data"]["market_cap_percentage"]["btc"]
                total_market_cap = data["data"]["total_market_cap"]["usd"]
                
                # BTC 主导地位信号
                if btc_dom > 55:
                    signal = "BTC 强势主导 (避险情绪)"
                elif btc_dom > 50:
                    signal = "BTC 相对强势"
                elif btc_dom > 45:
                    signal = "均衡"
                else:
                    signal = "山寨季 (风险偏好高)"
                
                return {
                    "btc_dominance": round(btc_dom, 2),
                    "total_market_cap_b": round(total_market_cap / 1e9, 1),
                    "signal": signal
                }
        except Exception as e:
            return {"error": str(e)}
        
        return {"error": "No data"}
    
    def get_upcoming_events(self) -> list:
        """获取近期重要事件 (从 API 抓取)"""
        today = datetime.now(timezone(timedelta(hours=8))).date()
        
        events = []
        
        # 尝试从 ForexFactory API 获取
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            for item in data:
                # 只关注 USD 高影响事件
                if item.get("country") == "USD" and item.get("impact") in ["High", "Medium"]:
                    event_date = item.get("date", "")[:10]  # 取日期部分
                    event_title = item.get("title", "")
                    importance = "high" if item.get("impact") == "High" else "medium"
                    
                    events.append({
                        "date": event_date,
                        "event": event_title,
                        "importance": importance,
                        "time": event_date[11:16] if len(event_date) > 10 else "-"
                    })
        except:
            pass
        
        # 补充固定日程 (FOMC 等)
        fixed_events = [
            {"date": "2026-03-14", "event": "密歇根消费者信心", "importance": "medium", "time": "23:00 SGT"},
            {"date": "2026-03-18", "event": "FOMC 会议开始", "importance": "high", "time": "-"},
            {"date": "2026-03-19", "event": "FOMC 利率决议", "importance": "critical", "time": "02:00 SGT"},
            {"date": "2026-03-28", "event": "PCE 物价指数", "importance": "high", "time": "21:30 SGT"},
        ]
        
        # 合并去重
        seen = set()
        for e in fixed_events:
            key = e["date"] + e["event"]
            if key not in seen:
                events.append(e)
                seen.add(key)
        
        # 筛选未来7天
        today_str = today.isoformat()
        future_7d = (today + timedelta(days=7)).isoformat()
        
        upcoming = [e for e in events if today_str <= e["date"] <= future_7d]
        return upcoming
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 收集数据
        fear_greed = self.get_fear_greed()
        btc_dom = self.get_btc_dominance()
        events = self.get_upcoming_events()
        
        # 综合判断
        signals = []
        
        # Fear & Greed 信号
        if "impact" in fear_greed:
            if fear_greed["impact"] == "bullish":
                signals.append(("bullish", 2 if fear_greed["value"] <= 20 else 1))
            elif fear_greed["impact"] == "bearish":
                signals.append(("bearish", 2 if fear_greed["value"] >= 80 else 1))
        
        # 计算综合倾向
        bull_score = sum(s[1] for s in signals if s[0] == "bullish")
        bear_score = sum(s[1] for s in signals if s[0] == "bearish")
        
        if bull_score > bear_score:
            bias = "bullish"
            confidence = min(5 + bull_score, 10)
        elif bear_score > bull_score:
            bias = "bearish"
            confidence = min(5 + bear_score, 10)
        else:
            bias = "neutral"
            confidence = 5
        
        # 风险环境
        if "value" in fear_greed:
            if fear_greed["value"] < 30:
                risk_env = "risk-off"
            elif fear_greed["value"] > 60:
                risk_env = "risk-on"
            else:
                risk_env = "mixed"
        else:
            risk_env = "unknown"
        
        # 要点
        key_points = []
        if "value" in fear_greed:
            key_points.append(f"Fear & Greed {fear_greed['value']} ({fear_greed.get('classification', '')})")
        if "btc_dominance" in btc_dom:
            key_points.append(f"BTC 主导率 {btc_dom['btc_dominance']}%")
        
        # 今日事件警告
        today_str = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        today_events = [e for e in events if e["date"] == today_str]
        alerts = []
        for e in today_events:
            if e["importance"] in ["high", "critical"]:
                alerts.append(f"⚠️ 今日 {e['time']}: {e['event']}")
        
        return {
            "agent": "macro",
            "timestamp": timestamp,
            "bias": bias,
            "confidence": confidence,
            "risk_environment": risk_env,
            "fear_greed": fear_greed,
            "btc_dominance": btc_dom,
            "upcoming_events": events,
            "key_points": key_points,
            "alerts": alerts
        }


def main():
    analyst = MacroAnalyst()
    result = analyst.analyze()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
