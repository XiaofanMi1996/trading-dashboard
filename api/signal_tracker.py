#!/usr/bin/env python3
"""
Signal Tracker - 信号记录与验证系统
记录每次喊单/建议，追踪结果，统计各 Agent 准确率
"""

import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path

# 数据存储路径
DATA_DIR = Path(__file__).parent.parent / "data"
SIGNALS_FILE = DATA_DIR / "signals.json"
STATS_FILE = DATA_DIR / "agent_stats.json"


def ensure_data_dir():
    """确保数据目录存在"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_signals() -> List[Dict]:
    """加载历史信号"""
    ensure_data_dir()
    if SIGNALS_FILE.exists():
        with open(SIGNALS_FILE, 'r') as f:
            return json.load(f)
    return []


def save_signals(signals: List[Dict]):
    """保存信号"""
    ensure_data_dir()
    with open(SIGNALS_FILE, 'w') as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)


def load_agent_stats() -> Dict:
    """加载 Agent 统计"""
    ensure_data_dir()
    if STATS_FILE.exists():
        with open(STATS_FILE, 'r') as f:
            return json.load(f)
    return {
        "derivatives": {"correct": 0, "wrong": 0, "weight": 2.5},
        "technical": {"correct": 0, "wrong": 0, "weight": 2.5},
        "orderflow": {"correct": 0, "wrong": 0, "weight": 2.0},
        "options": {"correct": 0, "wrong": 0, "weight": 1.5},
        "macro": {"correct": 0, "wrong": 0, "weight": 1.0},
        "onchain": {"correct": 0, "wrong": 0, "weight": 0.5},
        "overall": {"correct": 0, "wrong": 0, "total_pnl": 0}
    }


def save_agent_stats(stats: Dict):
    """保存 Agent 统计"""
    ensure_data_dir()
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)


def record_signal(
    direction: str,  # "long" or "short"
    entry_price: float,
    stop_loss: float,
    take_profit_1: float,
    take_profit_2: Optional[float] = None,
    symbol: str = "BTCUSDT",
    agent_biases: Optional[Dict[str, str]] = None,  # 各 Agent 当时的观点
    signal_score: Optional[float] = None,
    notes: Optional[str] = None
) -> Dict:
    """
    记录一个新信号
    
    agent_biases 格式: {"technical": "bullish", "derivatives": "neutral", ...}
    """
    timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
    
    signal = {
        "id": f"SIG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": timestamp,
        "symbol": symbol,
        "direction": direction,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "signal_score": signal_score,
        "agent_biases": agent_biases or {},
        "notes": notes,
        "status": "open",  # open / tp1_hit / tp2_hit / stopped / expired / cancelled
        "result": None,  # win / loss / breakeven
        "pnl_percent": None,
        "closed_at": None,
        "closed_price": None
    }
    
    signals = load_signals()
    signals.append(signal)
    save_signals(signals)
    
    return signal


def update_signal_result(
    signal_id: str,
    status: str,
    closed_price: float,
    result: str,  # "win" / "loss" / "breakeven"
    pnl_percent: float
):
    """更新信号结果"""
    signals = load_signals()
    
    for sig in signals:
        if sig["id"] == signal_id:
            sig["status"] = status
            sig["closed_price"] = closed_price
            sig["result"] = result
            sig["pnl_percent"] = pnl_percent
            sig["closed_at"] = datetime.now(timezone(timedelta(hours=8))).isoformat()
            break
    
    save_signals(signals)
    
    # 更新 Agent 统计
    _update_agent_stats(sig, result)


def _update_agent_stats(signal: Dict, result: str):
    """根据信号结果更新各 Agent 统计"""
    stats = load_agent_stats()
    direction = signal.get("direction")
    agent_biases = signal.get("agent_biases", {})
    
    is_win = result == "win"
    
    for agent, bias in agent_biases.items():
        if agent not in stats:
            stats[agent] = {"correct": 0, "wrong": 0, "weight": 1.0}
        
        # 判断该 Agent 是否正确
        agent_correct = False
        if direction == "long" and bias == "bullish" and is_win:
            agent_correct = True
        elif direction == "short" and bias == "bearish" and is_win:
            agent_correct = True
        elif direction == "long" and bias == "bearish" and not is_win:
            agent_correct = True  # Agent 说空，结果确实亏了
        elif direction == "short" and bias == "bullish" and not is_win:
            agent_correct = True
        
        if agent_correct:
            stats[agent]["correct"] += 1
        else:
            stats[agent]["wrong"] += 1
    
    # 更新总体统计
    if is_win:
        stats["overall"]["correct"] += 1
    else:
        stats["overall"]["wrong"] += 1
    
    pnl = signal.get("pnl_percent", 0)
    stats["overall"]["total_pnl"] = stats["overall"].get("total_pnl", 0) + pnl
    
    save_agent_stats(stats)


def check_open_signals(current_price: float) -> List[Dict]:
    """
    检查所有开放信号，看是否触发 TP/SL
    返回需要更新的信号列表
    """
    signals = load_signals()
    triggered = []
    
    for sig in signals:
        if sig["status"] != "open":
            continue
        
        entry = sig["entry_price"]
        sl = sig["stop_loss"]
        tp1 = sig["take_profit_1"]
        tp2 = sig.get("take_profit_2")
        direction = sig["direction"]
        
        if direction == "long":
            # 做多：价格 >= TP 或 <= SL
            if current_price <= sl:
                pnl = (sl - entry) / entry * 100
                triggered.append({
                    "signal": sig,
                    "status": "stopped",
                    "result": "loss",
                    "closed_price": sl,
                    "pnl_percent": round(pnl, 2)
                })
            elif current_price >= tp1:
                pnl = (tp1 - entry) / entry * 100
                triggered.append({
                    "signal": sig,
                    "status": "tp1_hit",
                    "result": "win",
                    "closed_price": tp1,
                    "pnl_percent": round(pnl, 2)
                })
        
        elif direction == "short":
            # 做空：价格 <= TP 或 >= SL
            if current_price >= sl:
                pnl = (entry - sl) / entry * 100
                triggered.append({
                    "signal": sig,
                    "status": "stopped",
                    "result": "loss",
                    "closed_price": sl,
                    "pnl_percent": round(pnl, 2)
                })
            elif current_price <= tp1:
                pnl = (entry - tp1) / entry * 100
                triggered.append({
                    "signal": sig,
                    "status": "tp1_hit",
                    "result": "win",
                    "closed_price": tp1,
                    "pnl_percent": round(pnl, 2)
                })
    
    return triggered


def get_stats_summary() -> Dict:
    """获取统计摘要"""
    stats = load_agent_stats()
    signals = load_signals()
    
    # 计算各 Agent 胜率
    agent_winrates = {}
    for agent, data in stats.items():
        if agent == "overall":
            continue
        total = data["correct"] + data["wrong"]
        if total > 0:
            winrate = data["correct"] / total * 100
            agent_winrates[agent] = {
                "winrate": round(winrate, 1),
                "total": total,
                "correct": data["correct"],
                "wrong": data["wrong"],
                "weight": data.get("weight", 1.0)
            }
    
    # 总体统计
    overall = stats.get("overall", {})
    total_trades = overall.get("correct", 0) + overall.get("wrong", 0)
    overall_winrate = 0
    if total_trades > 0:
        overall_winrate = overall.get("correct", 0) / total_trades * 100
    
    # 近期信号
    open_signals = [s for s in signals if s["status"] == "open"]
    closed_signals = [s for s in signals if s["status"] != "open"]
    recent_closed = sorted(closed_signals, key=lambda x: x.get("closed_at", ""), reverse=True)[:10]
    
    return {
        "overall": {
            "total_trades": total_trades,
            "wins": overall.get("correct", 0),
            "losses": overall.get("wrong", 0),
            "winrate": round(overall_winrate, 1),
            "total_pnl": round(overall.get("total_pnl", 0), 2)
        },
        "agent_winrates": agent_winrates,
        "open_signals": len(open_signals),
        "recent_trades": recent_closed
    }


def adjust_weights_by_performance():
    """根据历史表现自动调整 Agent 权重"""
    stats = load_agent_stats()
    
    base_weights = {
        "derivatives": 2.5,
        "technical": 2.5,
        "orderflow": 2.0,
        "options": 1.5,
        "macro": 1.0,
        "onchain": 0.5
    }
    
    for agent, base in base_weights.items():
        if agent not in stats:
            continue
        
        data = stats[agent]
        total = data["correct"] + data["wrong"]
        
        if total < 5:
            # 样本不足，保持原权重
            stats[agent]["weight"] = base
        else:
            winrate = data["correct"] / total
            # 胜率调整：50% 为基准，每偏离 10% 调整 20% 权重
            adjustment = (winrate - 0.5) * 2  # -1 到 +1
            new_weight = base * (1 + adjustment * 0.5)  # 最多 ±50%
            stats[agent]["weight"] = round(max(0.1, min(5.0, new_weight)), 2)
    
    save_agent_stats(stats)
    return stats


def format_stats_report() -> str:
    """格式化统计报告"""
    summary = get_stats_summary()
    
    lines = []
    lines.append("📊 **信号追踪统计**")
    lines.append("")
    
    overall = summary["overall"]
    lines.append(f"**总体表现**")
    lines.append(f"• 总交易: {overall['total_trades']}")
    lines.append(f"• 胜率: {overall['winrate']}% ({overall['wins']}胜 / {overall['losses']}负)")
    lines.append(f"• 累计盈亏: {overall['total_pnl']:+.2f}%")
    lines.append(f"• 开放信号: {summary['open_signals']}")
    lines.append("")
    
    if summary["agent_winrates"]:
        lines.append("**各 Agent 准确率**")
        for agent, data in sorted(summary["agent_winrates"].items(), key=lambda x: x[1]["winrate"], reverse=True):
            emoji = "🟢" if data["winrate"] >= 55 else "🔴" if data["winrate"] < 45 else "⚪"
            lines.append(f"• {emoji} {agent}: {data['winrate']}% ({data['total']}次) 权重:{data['weight']}")
    
    return "\n".join(lines)


# CLI 测试
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "stats":
            print(format_stats_report())
        
        elif cmd == "check":
            # 检查开放信号
            price = float(sys.argv[2]) if len(sys.argv) > 2 else 71000
            triggered = check_open_signals(price)
            if triggered:
                print(f"触发 {len(triggered)} 个信号:")
                for t in triggered:
                    print(f"  {t['signal']['id']}: {t['status']} @ ${t['closed_price']} ({t['pnl_percent']:+.2f}%)")
            else:
                print("无信号触发")
        
        elif cmd == "adjust":
            # 调整权重
            stats = adjust_weights_by_performance()
            print("权重已调整:")
            for agent in ["derivatives", "technical", "orderflow", "options", "macro", "onchain"]:
                if agent in stats:
                    print(f"  {agent}: {stats[agent]['weight']}")
        
        elif cmd == "record":
            # 记录测试信号
            sig = record_signal(
                direction="short",
                entry_price=73000,
                stop_loss=74000,
                take_profit_1=70000,
                agent_biases={"technical": "bearish", "macro": "bullish"},
                signal_score=2.5,
                notes="测试信号"
            )
            print(f"已记录: {sig['id']}")
        
        else:
            print(f"未知命令: {cmd}")
            print("可用命令: stats, check <price>, adjust, record")
    
    else:
        print(format_stats_report())
