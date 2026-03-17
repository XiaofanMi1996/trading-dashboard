#!/usr/bin/env python3
"""
Trade Journal - 交易日志和复盘学习
- 记录每笔交易时的系统判断
- 交易结束后自动复盘
- 分析信号准确率，调整权重
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

class TradeJournal:
    def __init__(self):
        self.base_dir = os.path.dirname(__file__)
        self.journal_file = os.path.join(self.base_dir, "../data/trade_journal.json")
        self.stats_file = os.path.join(self.base_dir, "../data/signal_stats.json")
        
    def load_journal(self) -> List[Dict]:
        try:
            with open(self.journal_file, "r") as f:
                return json.load(f)
        except:
            return []
    
    def save_journal(self, journal: List[Dict]):
        os.makedirs(os.path.dirname(self.journal_file), exist_ok=True)
        with open(self.journal_file, "w") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)
    
    def load_stats(self) -> Dict:
        try:
            with open(self.stats_file, "r") as f:
                return json.load(f)
        except:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "signal_accuracy": {
                    "derivatives": {"correct": 0, "total": 0},
                    "technical": {"correct": 0, "total": 0},
                    "orderflow": {"correct": 0, "total": 0},
                    "options": {"correct": 0, "total": 0},
                    "macro": {"correct": 0, "total": 0},
                    "onchain": {"correct": 0, "total": 0}
                },
                "pattern_accuracy": {
                    "short_squeeze": {"correct": 0, "total": 0},
                    "rejection": {"correct": 0, "total": 0},
                    "momentum": {"correct": 0, "total": 0},
                    "testing": {"correct": 0, "total": 0}
                }
            }
    
    def save_stats(self, stats: Dict):
        os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
        with open(self.stats_file, "w") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    
    def record_entry(self, trade: Dict) -> str:
        """
        记录开仓时的信息
        trade = {
            "id": "2026-03-17-001",
            "direction": "short",
            "entry_price": 75696,
            "entry_time": "2026-03-17T09:54:00+08:00",
            "zone": "第一压力区",
            "market_nature": "轧空行情",
            "system_recommendation": "观望",
            "system_signal_score": 5.3,
            "agent_signals": {
                "derivatives": "neutral",
                "technical": "bullish",
                "orderflow": "bullish",
                ...
            },
            "candle_pattern": "无明确信号",
            "user_reasoning": "4H插针明显",
            "stop_loss": 76500,
            "take_profit": [73200, 72500]
        }
        """
        journal = self.load_journal()
        
        trade["status"] = "open"
        trade["recorded_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        journal.append(trade)
        self.save_journal(journal)
        
        return trade["id"]
    
    def record_exit(self, trade_id: str, exit_info: Dict) -> Dict:
        """
        记录平仓信息并自动复盘
        exit_info = {
            "exit_price": 74200,
            "exit_time": "2026-03-17T12:00:00+08:00",
            "exit_reason": "止盈1",
            "pnl_percent": 1.97,
            "pnl_dollar": 195
        }
        """
        journal = self.load_journal()
        
        # 找到对应交易
        trade = None
        for t in journal:
            if t.get("id") == trade_id:
                trade = t
                break
        
        if not trade:
            return {"error": "Trade not found"}
        
        # 更新交易信息
        trade.update(exit_info)
        trade["status"] = "closed"
        
        # 自动复盘
        review = self.auto_review(trade)
        trade["review"] = review
        
        self.save_journal(journal)
        
        # 更新统计
        self.update_stats(trade)
        
        return review
    
    def auto_review(self, trade: Dict) -> Dict:
        """自动复盘分析"""
        is_win = trade.get("pnl_dollar", 0) > 0
        direction = trade.get("direction", "")
        
        review = {
            "result": "盈利" if is_win else "亏损",
            "system_was_right": False,
            "user_was_right": is_win,
            "lessons": []
        }
        
        # 检查系统建议是否正确
        system_rec = trade.get("system_recommendation", "").lower()
        if direction == "short":
            if "空" in system_rec and is_win:
                review["system_was_right"] = True
            elif "观望" in system_rec and not is_win:
                review["system_was_right"] = True
                review["lessons"].append("系统建议观望是对的，不该开仓")
        elif direction == "long":
            if "多" in system_rec and is_win:
                review["system_was_right"] = True
            elif "观望" in system_rec and not is_win:
                review["system_was_right"] = True
                review["lessons"].append("系统建议观望是对的，不该开仓")
        
        # 分析哪个信号准确
        agent_signals = trade.get("agent_signals", {})
        correct_agents = []
        wrong_agents = []
        
        for agent, signal in agent_signals.items():
            if direction == "short":
                expected_correct = signal in ["bearish", "neutral"]
            else:
                expected_correct = signal in ["bullish", "neutral"]
            
            if is_win:
                if direction == "short" and signal == "bearish":
                    correct_agents.append(agent)
                elif direction == "long" and signal == "bullish":
                    correct_agents.append(agent)
                elif signal == "neutral":
                    pass  # 中性不计
                else:
                    wrong_agents.append(agent)
            else:
                if signal != "neutral":
                    if direction == "short" and signal == "bullish":
                        correct_agents.append(agent)  # 它说对了不该空
                    elif direction == "long" and signal == "bearish":
                        correct_agents.append(agent)
        
        review["correct_agents"] = correct_agents
        review["wrong_agents"] = wrong_agents
        
        # 生成教训
        if is_win and not review["system_was_right"]:
            review["lessons"].append(f"用户判断优于系统，参考了: {trade.get('user_reasoning', 'N/A')}")
        
        if trade.get("market_nature") == "short_squeeze" and direction == "short" and is_win:
            review["lessons"].append("轧空行情中做空成功，说明等到了插针确认")
        
        return review
    
    def update_stats(self, trade: Dict):
        """更新信号统计"""
        stats = self.load_stats()
        
        is_win = trade.get("pnl_dollar", 0) > 0
        direction = trade.get("direction", "")
        
        stats["total_trades"] += 1
        if is_win:
            stats["wins"] += 1
        else:
            stats["losses"] += 1
        
        # 更新各 Agent 准确率
        agent_signals = trade.get("agent_signals", {})
        for agent, signal in agent_signals.items():
            if agent in stats["signal_accuracy"]:
                stats["signal_accuracy"][agent]["total"] += 1
                
                # 判断是否正确
                was_correct = False
                if direction == "short" and is_win and signal == "bearish":
                    was_correct = True
                elif direction == "long" and is_win and signal == "bullish":
                    was_correct = True
                elif not is_win and signal == "neutral":
                    was_correct = True  # 建议观望且亏损 = 正确
                
                if was_correct:
                    stats["signal_accuracy"][agent]["correct"] += 1
        
        # 更新盘面性质准确率
        nature = trade.get("market_nature", "")
        if nature in stats["pattern_accuracy"]:
            stats["pattern_accuracy"][nature]["total"] += 1
            
            # 如果在该性质下开仓并盈利
            if is_win:
                stats["pattern_accuracy"][nature]["correct"] += 1
        
        self.save_stats(stats)
    
    def get_accuracy_report(self) -> str:
        """生成准确率报告"""
        stats = self.load_stats()
        
        lines = []
        lines.append("📊 **信号准确率报告**")
        lines.append("")
        
        total = stats["total_trades"]
        if total == 0:
            lines.append("暂无交易记录")
            return "\n".join(lines)
        
        win_rate = stats["wins"] / total * 100
        lines.append(f"总交易: {total} | 胜率: {win_rate:.1f}%")
        lines.append("")
        
        lines.append("**各 Agent 准确率：**")
        for agent, data in stats["signal_accuracy"].items():
            if data["total"] > 0:
                acc = data["correct"] / data["total"] * 100
                lines.append(f"• {agent}: {acc:.0f}% ({data['correct']}/{data['total']})")
        
        lines.append("")
        lines.append("**盘面性质准确率：**")
        for pattern, data in stats["pattern_accuracy"].items():
            if data["total"] > 0:
                acc = data["correct"] / data["total"] * 100
                lines.append(f"• {pattern}: {acc:.0f}% ({data['correct']}/{data['total']})")
        
        return "\n".join(lines)


def main():
    journal = TradeJournal()
    
    # 示例：记录今天的交易
    # journal.record_entry({...})
    
    # 查看统计
    print(journal.get_accuracy_report())


if __name__ == "__main__":
    main()
