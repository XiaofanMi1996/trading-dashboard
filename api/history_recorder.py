#!/usr/bin/env python3
"""
History Recorder - 分析历史记录系统
保存每次分析结果，方便复盘
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

class HistoryRecorder:
    def __init__(self):
        self.base_dir = os.path.join(os.path.dirname(__file__), "../reports")
        os.makedirs(self.base_dir, exist_ok=True)
    
    def _get_daily_file(self, date: Optional[str] = None) -> str:
        """获取日报告文件路径"""
        if not date:
            date = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
        return os.path.join(self.base_dir, f"analysis_{date}.json")
    
    def save_analysis(self, analysis: Dict[str, Any], trigger: str = "manual") -> str:
        """保存分析结果"""
        timestamp = datetime.now(timezone(timedelta(hours=8)))
        
        record = {
            "id": timestamp.strftime("%Y%m%d_%H%M%S"),
            "timestamp": timestamp.isoformat(),
            "trigger": trigger,  # manual / scheduled / price_trigger
            "analysis": analysis
        }
        
        # 读取现有记录
        daily_file = self._get_daily_file()
        try:
            with open(daily_file, "r") as f:
                records = json.load(f)
        except:
            records = []
        
        # 添加新记录
        records.append(record)
        
        # 保存
        with open(daily_file, "w") as f:
            json.dump(records, f, indent=2, ensure_ascii=False)
        
        return record["id"]
    
    def get_daily_records(self, date: Optional[str] = None) -> List[Dict]:
        """获取某日所有记录"""
        daily_file = self._get_daily_file(date)
        try:
            with open(daily_file, "r") as f:
                return json.load(f)
        except:
            return []
    
    def get_latest(self, count: int = 5) -> List[Dict]:
        """获取最近N条记录"""
        today = datetime.now(timezone(timedelta(hours=8)))
        all_records = []
        
        # 查找最近7天的记录
        for i in range(7):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            records = self.get_daily_records(date)
            all_records.extend(records)
            if len(all_records) >= count:
                break
        
        # 按时间倒序
        all_records.sort(key=lambda x: x["timestamp"], reverse=True)
        return all_records[:count]
    
    def get_record_by_id(self, record_id: str) -> Optional[Dict]:
        """根据ID获取记录"""
        date = record_id[:8]  # 20260312
        date_formatted = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        records = self.get_daily_records(date_formatted)
        
        for r in records:
            if r["id"] == record_id:
                return r
        return None
    
    def compare_records(self, id1: str, id2: str) -> Dict[str, Any]:
        """对比两条记录"""
        r1 = self.get_record_by_id(id1)
        r2 = self.get_record_by_id(id2)
        
        if not r1 or not r2:
            return {"error": "记录不存在"}
        
        def get_bias(r):
            return r.get("analysis", {}).get("synthesis", {}).get("bias", "unknown")
        
        def get_price(r):
            return r.get("analysis", {}).get("price", 0)
        
        def get_confidence(r):
            return r.get("analysis", {}).get("synthesis", {}).get("confidence", 0)
        
        return {
            "record_1": {
                "id": id1,
                "timestamp": r1["timestamp"],
                "price": get_price(r1),
                "bias": get_bias(r1),
                "confidence": get_confidence(r1)
            },
            "record_2": {
                "id": id2,
                "timestamp": r2["timestamp"],
                "price": get_price(r2),
                "bias": get_bias(r2),
                "confidence": get_confidence(r2)
            },
            "price_change": get_price(r2) - get_price(r1),
            "bias_changed": get_bias(r1) != get_bias(r2)
        }
    
    def get_accuracy_stats(self, days: int = 7) -> Dict[str, Any]:
        """统计准确率 (需要人工标记结果)"""
        # TODO: 实现结果标记和准确率统计
        return {"note": "功能待实现 - 需要人工标记每次分析的实际结果"}
    
    def generate_daily_summary(self, date: Optional[str] = None) -> str:
        """生成每日汇总"""
        records = self.get_daily_records(date)
        
        if not records:
            return "当日无分析记录"
        
        lines = [f"📊 分析记录汇总 ({date or '今日'})", ""]
        lines.append(f"总计 {len(records)} 次分析")
        lines.append("")
        
        for r in records:
            time = r["timestamp"].split("T")[1][:5]
            trigger = r["trigger"]
            analysis = r.get("analysis", {})
            synthesis = analysis.get("synthesis", {})
            bias = synthesis.get("bias", "?")
            confidence = synthesis.get("confidence", 0)
            price = analysis.get("price", 0)
            
            bias_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(bias, "❓")
            lines.append(f"{time} | {bias_emoji} {bias.upper()} ({confidence}/10) | ${price:,.0f} | {trigger}")
        
        return "\n".join(lines)


def main():
    recorder = HistoryRecorder()
    
    # 测试
    print("最近记录:", json.dumps(recorder.get_latest(3), indent=2, ensure_ascii=False))
    print("\n每日汇总:")
    print(recorder.generate_daily_summary())


if __name__ == "__main__":
    main()
