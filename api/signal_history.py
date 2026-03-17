#!/usr/bin/env python3
"""
Signal History - 预警历史记录和统计
记录每次预警、实际结果、各 Agent 表现
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional


class SignalHistory:
    def __init__(self):
        self.base_dir = os.path.dirname(__file__)
        self.history_file = os.path.join(self.base_dir, "../data/signal_history.json")
        self.stats_file = os.path.join(self.base_dir, "../data/signal_stats.json")
    
    def load_history(self) -> List[Dict]:
        """加载历史记录"""
        try:
            with open(self.history_file, "r") as f:
                return json.load(f)
        except:
            return []
    
    def save_history(self, history: List[Dict]):
        """保存历史记录"""
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        # 只保留最近 500 条
        with open(self.history_file, "w") as f:
            json.dump(history[-500:], f, indent=2, ensure_ascii=False)
    
    def record_signal(self, signal: Dict):
        """
        记录一次预警信号，同时创建模拟仓位
        
        signal 格式:
        {
            "timestamp": "2026-03-16T16:30:00+08:00",
            "price": 73500,
            "type": "entry" | "position",
            "direction": "long" | "short",
            "level_name": "4H EMA300",
            "level_price": 73200,
            "suggestion": "做空",
            "agent_votes": {
                "derivatives": "bullish",
                "technical": "neutral",
                ...
            },
            "confidence": "高" | "中" | "低",
            "framework_direction": "主空"
        }
        """
        history = self.load_history()
        
        signal["id"] = f"sig_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(history)}"
        signal["status"] = "open"  # open, win, loss, cancelled
        signal["result"] = None
        signal["closed_at"] = None
        signal["closed_price"] = None
        signal["pnl_pct"] = None
        
        # 模拟仓位设置 - 使用外部传入的结构化止盈止损
        # 如果没传入，用默认逻辑
        if "sim_entry" not in signal:
            signal["sim_entry"] = signal.get("price", 0)
        if "sim_sl" not in signal:
            entry_price = signal.get("price", 0)
            level_price = signal.get("level_price", entry_price)
            direction = signal.get("direction", "")
            if direction == "short":
                signal["sim_sl"] = level_price * 1.01
                signal["sim_tp1"] = entry_price * 0.985
            elif direction == "long":
                signal["sim_sl"] = level_price * 0.99
                signal["sim_tp1"] = entry_price * 1.015
        
        history.append(signal)
        self.save_history(history)
        
        return signal["id"]
    
    def update_signal_result(self, signal_id: str, result: str, closed_price: float):
        """
        更新信号结果
        
        result: "win" | "loss" | "cancelled"
        """
        history = self.load_history()
        
        for sig in history:
            if sig.get("id") == signal_id:
                sig["status"] = result
                sig["result"] = result
                sig["closed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
                sig["closed_price"] = closed_price
                
                # 计算盈亏
                entry_price = sig.get("price", 0)
                direction = sig.get("direction", "")
                if entry_price and direction:
                    if direction == "short":
                        pnl = (entry_price - closed_price) / entry_price * 100
                    else:
                        pnl = (closed_price - entry_price) / entry_price * 100
                    sig["pnl_pct"] = round(pnl, 2)
                
                break
        
        self.save_history(history)
        self._update_stats(history)
    
    def _update_stats(self, history: List[Dict]):
        """更新统计数据"""
        stats = {
            "total_signals": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "by_confidence": {
                "高": {"total": 0, "wins": 0},
                "中": {"total": 0, "wins": 0},
                "低": {"total": 0, "wins": 0}
            },
            "by_agent": {},
            "by_level_type": {},
            "avg_pnl_win": 0,
            "avg_pnl_loss": 0
        }
        
        closed_signals = [s for s in history if s.get("status") in ["win", "loss"]]
        
        if not closed_signals:
            self._save_stats(stats)
            return
        
        stats["total_signals"] = len(closed_signals)
        stats["wins"] = len([s for s in closed_signals if s["status"] == "win"])
        stats["losses"] = len([s for s in closed_signals if s["status"] == "loss"])
        stats["win_rate"] = round(stats["wins"] / stats["total_signals"] * 100, 1) if stats["total_signals"] > 0 else 0
        
        # 按置信度统计
        for conf in ["高", "中", "低"]:
            conf_signals = [s for s in closed_signals if s.get("confidence") == conf]
            stats["by_confidence"][conf]["total"] = len(conf_signals)
            stats["by_confidence"][conf]["wins"] = len([s for s in conf_signals if s["status"] == "win"])
        
        # 按 Agent 统计
        for sig in closed_signals:
            agent_votes = sig.get("agent_votes", {})
            direction = sig.get("direction", "")
            expected = "bearish" if direction == "short" else "bullish"
            is_win = sig["status"] == "win"
            
            for agent, vote in agent_votes.items():
                if agent not in stats["by_agent"]:
                    stats["by_agent"][agent] = {"correct": 0, "total": 0, "accuracy": 0}
                
                stats["by_agent"][agent]["total"] += 1
                
                # Agent 判断正确的情况：
                # 1. 信号赢了且 Agent 支持该方向
                # 2. 信号输了且 Agent 反对该方向
                agent_supported = (vote == expected)
                if (is_win and agent_supported) or (not is_win and not agent_supported and vote != "neutral"):
                    stats["by_agent"][agent]["correct"] += 1
        
        # 计算各 Agent 准确率
        for agent in stats["by_agent"]:
            total = stats["by_agent"][agent]["total"]
            correct = stats["by_agent"][agent]["correct"]
            stats["by_agent"][agent]["accuracy"] = round(correct / total * 100, 1) if total > 0 else 0
        
        # 按关键位类型统计
        for sig in closed_signals:
            level_name = sig.get("level_name", "unknown")
            # 提取类型 (EMA, 布林, swing 等)
            if "EMA" in level_name:
                level_type = "EMA"
            elif "布林" in level_name:
                level_type = "布林带"
            elif "高点" in level_name or "低点" in level_name:
                level_type = "前高前低"
            else:
                level_type = "其他"
            
            if level_type not in stats["by_level_type"]:
                stats["by_level_type"][level_type] = {"total": 0, "wins": 0, "win_rate": 0}
            
            stats["by_level_type"][level_type]["total"] += 1
            if sig["status"] == "win":
                stats["by_level_type"][level_type]["wins"] += 1
        
        for lt in stats["by_level_type"]:
            total = stats["by_level_type"][lt]["total"]
            wins = stats["by_level_type"][lt]["wins"]
            stats["by_level_type"][lt]["win_rate"] = round(wins / total * 100, 1) if total > 0 else 0
        
        # 平均盈亏
        win_pnls = [s["pnl_pct"] for s in closed_signals if s["status"] == "win" and s.get("pnl_pct")]
        loss_pnls = [s["pnl_pct"] for s in closed_signals if s["status"] == "loss" and s.get("pnl_pct")]
        
        stats["avg_pnl_win"] = round(sum(win_pnls) / len(win_pnls), 2) if win_pnls else 0
        stats["avg_pnl_loss"] = round(sum(loss_pnls) / len(loss_pnls), 2) if loss_pnls else 0
        
        self._save_stats(stats)
    
    def _save_stats(self, stats: Dict):
        """保存统计数据"""
        os.makedirs(os.path.dirname(self.stats_file), exist_ok=True)
        with open(self.stats_file, "w") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
    
    def get_stats(self) -> Dict:
        """获取统计数据"""
        try:
            with open(self.stats_file, "r") as f:
                return json.load(f)
        except:
            return {}
    
    def get_open_signals(self) -> List[Dict]:
        """获取未关闭的信号"""
        history = self.load_history()
        return [s for s in history if s.get("status") == "open"]
    
    def check_and_close_signals(self, current_price: float) -> List[Dict]:
        """检查模拟仓位是否触发止盈止损"""
        history = self.load_history()
        closed_signals = []
        
        for sig in history:
            if sig.get("status") != "open":
                continue
            
            direction = sig.get("direction", "")
            sim_sl = sig.get("sim_sl", 0)
            sim_tp1 = sig.get("sim_tp1", 0)
            sim_tp2 = sig.get("sim_tp2", 0)
            entry = sig.get("sim_entry", sig.get("price", 0))
            
            if not direction or not entry:
                continue
            
            result = None
            closed_price = current_price
            
            if direction == "short":
                # 空单：价格涨到止损 = 亏，价格跌到止盈 = 赢
                if current_price >= sim_sl:
                    result = "loss"
                elif current_price <= sim_tp1:
                    result = "win"
            elif direction == "long":
                # 多单：价格跌到止损 = 亏，价格涨到止盈 = 赢
                if current_price <= sim_sl:
                    result = "loss"
                elif current_price >= sim_tp1:
                    result = "win"
            
            if result:
                sig["status"] = result
                sig["result"] = result
                sig["closed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
                sig["closed_price"] = closed_price
                
                # 计算盈亏
                if direction == "short":
                    pnl = (entry - closed_price) / entry * 100
                else:
                    pnl = (closed_price - entry) / entry * 100
                sig["pnl_pct"] = round(pnl, 2)
                
                closed_signals.append({
                    "signal": sig,
                    "result": result,
                    "pnl_percent": sig["pnl_pct"],
                    "entry": entry,
                    "closed_price": closed_price
                })
        
        if closed_signals:
            self.save_history(history)
            self._update_stats(history)
        
        return closed_signals
    
    def get_agent_weights(self) -> Dict[str, float]:
        """根据历史表现计算 Agent 权重"""
        stats = self.get_stats()
        agent_stats = stats.get("by_agent", {})
        
        if not agent_stats:
            # 默认权重
            return {
                "derivatives": 2.0,
                "technical": 2.0,
                "orderflow": 1.5,
                "options": 1.0,
                "macro": 1.0,
                "onchain": 0.5
            }
        
        # 根据准确率调整权重 (50% 准确率 = 1.0 权重, 70% = 2.0, 30% = 0.5)
        weights = {}
        for agent, data in agent_stats.items():
            accuracy = data.get("accuracy", 50)
            # 线性映射: accuracy 30-70 -> weight 0.5-2.0
            weight = 0.5 + (accuracy - 30) / 40 * 1.5
            weight = max(0.3, min(2.5, weight))  # 限制范围
            weights[agent] = round(weight, 2)
        
        return weights
    
    def format_stats_report(self) -> str:
        """格式化统计报告"""
        stats = self.get_stats()
        
        if not stats or stats.get("total_signals", 0) == 0:
            return "📊 暂无历史数据"
        
        lines = []
        lines.append("📊 **信号统计报告**")
        lines.append("")
        lines.append(f"总信号数: {stats['total_signals']}")
        lines.append(f"胜率: {stats['win_rate']}% ({stats['wins']}胜 / {stats['losses']}负)")
        lines.append(f"平均盈利: {stats['avg_pnl_win']:+.2f}% | 平均亏损: {stats['avg_pnl_loss']:+.2f}%")
        lines.append("")
        
        lines.append("**按置信度:**")
        for conf in ["高", "中", "低"]:
            data = stats["by_confidence"].get(conf, {})
            total = data.get("total", 0)
            wins = data.get("wins", 0)
            rate = round(wins / total * 100, 1) if total > 0 else 0
            lines.append(f"• {conf}: {rate}% ({wins}/{total})")
        lines.append("")
        
        lines.append("**Agent 准确率:**")
        agent_stats = stats.get("by_agent", {})
        sorted_agents = sorted(agent_stats.items(), key=lambda x: x[1].get("accuracy", 0), reverse=True)
        for agent, data in sorted_agents:
            lines.append(f"• {agent}: {data['accuracy']}% ({data['correct']}/{data['total']})")
        lines.append("")
        
        lines.append("**关键位类型胜率:**")
        for lt, data in stats.get("by_level_type", {}).items():
            lines.append(f"• {lt}: {data['win_rate']}% ({data['wins']}/{data['total']})")
        
        return "\n".join(lines)


def main():
    history = SignalHistory()
    print(history.format_stats_report())


if __name__ == "__main__":
    main()
