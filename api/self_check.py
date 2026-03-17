#!/usr/bin/env python3
"""
Self Check - 系统自检与动态调整
每次输出前自动校验，记录错误并迭代
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional

class SelfCheck:
    def __init__(self):
        self.log_file = os.path.join(os.path.dirname(__file__), "../data/self_check_log.json")
        self.rules_file = os.path.join(os.path.dirname(__file__), "../data/check_rules.json")
        
    def load_log(self) -> List[Dict]:
        try:
            with open(self.log_file, "r") as f:
                return json.load(f)
        except:
            return []
    
    def save_log(self, log: List[Dict]):
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        with open(self.log_file, "w") as f:
            json.dump(log[-100:], f, indent=2, ensure_ascii=False)  # 只保留最近100条
    
    def load_rules(self) -> Dict:
        try:
            with open(self.rules_file, "r") as f:
                return json.load(f)
        except:
            return self.default_rules()
    
    def default_rules(self) -> Dict:
        return {
            "price_data": {
                "rule": "所有价位必须实时计算，不用记忆",
                "check": "verify_realtime",
                "failures": 0,
                "last_failure": None
            },
            "signal_filter": {
                "rule": "喊单前检查RSI/布林/量价",
                "check": "verify_filters",
                "failures": 0,
                "last_failure": None
            },
            "date_time": {
                "rule": "日期时间必须跑session_status确认",
                "check": "verify_datetime",
                "failures": 0,
                "last_failure": None
            },
            "position_alert": {
                "rule": "价格进入关键EMA ±1%时主动提醒",
                "check": "verify_price_alert",
                "failures": 0,
                "last_failure": None
            }
        }
    
    def save_rules(self, rules: Dict):
        os.makedirs(os.path.dirname(self.rules_file), exist_ok=True)
        with open(self.rules_file, "w") as f:
            json.dump(rules, f, indent=2, ensure_ascii=False)
    
    def record_error(self, category: str, description: str, context: str = ""):
        """记录错误"""
        log = self.load_log()
        rules = self.load_rules()
        
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        error = {
            "timestamp": timestamp,
            "category": category,
            "description": description,
            "context": context
        }
        log.append(error)
        self.save_log(log)
        
        # 更新规则失败计数
        if category in rules:
            rules[category]["failures"] += 1
            rules[category]["last_failure"] = timestamp
            self.save_rules(rules)
        
        return error
    
    def get_error_summary(self) -> Dict:
        """获取错误统计"""
        log = self.load_log()
        rules = self.load_rules()
        
        summary = {
            "total_errors": len(log),
            "by_category": {},
            "rules": rules
        }
        
        for entry in log:
            cat = entry.get("category", "unknown")
            summary["by_category"][cat] = summary["by_category"].get(cat, 0) + 1
        
        return summary
    
    def add_rule(self, name: str, rule: str, check: str = "manual"):
        """动态添加规则"""
        rules = self.load_rules()
        rules[name] = {
            "rule": rule,
            "check": check,
            "failures": 0,
            "last_failure": None,
            "added": datetime.now(timezone(timedelta(hours=8))).isoformat()
        }
        self.save_rules(rules)
        return rules[name]
    
    def suggest_improvements(self) -> List[str]:
        """根据错误历史建议改进"""
        summary = self.get_error_summary()
        suggestions = []
        
        for cat, count in summary["by_category"].items():
            if count >= 2:
                rule = summary["rules"].get(cat, {})
                suggestions.append(f"⚠️ {cat} 错误 {count} 次: {rule.get('rule', '需要添加规则')}")
        
        return suggestions


class OutputValidator:
    """输出前校验器"""
    
    def __init__(self):
        self.checker = SelfCheck()
    
    def validate_price_output(self, prices: Dict[str, float], source: str) -> Dict:
        """校验价格输出"""
        result = {"valid": True, "issues": []}
        
        # 检查是否有来源标注
        if source not in ["realtime", "calculated"]:
            result["valid"] = False
            result["issues"].append("价格数据未标注实时来源")
            self.checker.record_error("price_data", "价格数据未标注来源", str(prices))
        
        return result
    
    def validate_signal(self, score: float, rsi: float, boll_pct: float, direction: str) -> Dict:
        """校验喊单信号"""
        result = {"valid": True, "issues": [], "blocked": False}
        
        if direction == "多":
            if rsi > 70:
                result["blocked"] = True
                result["issues"].append(f"RSI {rsi} 超买，不喊多")
            if boll_pct > 100:
                result["blocked"] = True
                result["issues"].append(f"布林 {boll_pct}% 破上轨，不追高")
        elif direction == "空":
            if rsi < 30:
                result["blocked"] = True
                result["issues"].append(f"RSI {rsi} 超卖，不喊空")
            if boll_pct < 0:
                result["blocked"] = True
                result["issues"].append(f"布林 {boll_pct}% 破下轨，不追空")
        
        return result


def main():
    checker = SelfCheck()
    
    # 初始化规则
    rules = checker.load_rules()
    if not rules:
        rules = checker.default_rules()
        checker.save_rules(rules)
    
    print("📋 Self Check 系统")
    print("=" * 40)
    
    summary = checker.get_error_summary()
    print(f"总错误数: {summary['total_errors']}")
    print(f"按类别: {summary['by_category']}")
    
    print("\n📜 当前规则:")
    for name, rule in summary["rules"].items():
        print(f"  • {name}: {rule['rule']} (失败 {rule['failures']} 次)")
    
    suggestions = checker.suggest_improvements()
    if suggestions:
        print("\n💡 改进建议:")
        for s in suggestions:
            print(f"  {s}")


if __name__ == "__main__":
    main()
