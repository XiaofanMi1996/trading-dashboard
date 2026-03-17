#!/usr/bin/env python3
"""
Signal CLI - 信号记录命令行工具
用法:
    python signal_cli.py record short 73000 74000 70000  # 记录做空信号
    python signal_cli.py stats                            # 查看统计
    python signal_cli.py check 71500                      # 检查信号触发
    python signal_cli.py list                             # 列出开放信号
    python signal_cli.py close SIG-xxx win 70000          # 手动关闭信号
"""

import sys
import json
from signal_tracker import (
    record_signal, 
    check_open_signals, 
    update_signal_result,
    get_stats_summary, 
    format_stats_report,
    load_signals,
    adjust_weights_by_performance
)
from trading_desk import TradingDesk


def cmd_record(args):
    """记录新信号"""
    if len(args) < 4:
        print("用法: record <direction> <entry> <stop_loss> <take_profit>")
        print("例如: record short 73000 74000 70000")
        return
    
    direction = args[0]  # long / short
    entry = float(args[1])
    sl = float(args[2])
    tp = float(args[3])
    tp2 = float(args[4]) if len(args) > 4 else None
    notes = " ".join(args[5:]) if len(args) > 5 else None
    
    # 获取当前各 Agent 观点
    desk = TradingDesk("BTCUSDT")
    analyses = desk.run_all_analysts()
    synthesis = desk.synthesize(analyses)
    
    agent_biases = synthesis.get("individual_biases", {})
    signal_score = synthesis.get("signal_score", {}).get("final_score", 0)
    
    sig = record_signal(
        direction=direction,
        entry_price=entry,
        stop_loss=sl,
        take_profit_1=tp,
        take_profit_2=tp2,
        agent_biases=agent_biases,
        signal_score=signal_score,
        notes=notes
    )
    
    print(f"✅ 已记录信号: {sig['id']}")
    print(f"   方向: {direction.upper()}")
    print(f"   入场: ${entry:,.0f}")
    print(f"   止损: ${sl:,.0f}")
    print(f"   止盈: ${tp:,.0f}")
    print(f"   评分: {signal_score:+.1f}")
    print(f"   Agent 观点: {agent_biases}")


def cmd_stats():
    """显示统计"""
    print(format_stats_report())


def cmd_check(args):
    """检查信号触发"""
    if not args:
        print("用法: check <current_price>")
        return
    
    price = float(args[0])
    triggered = check_open_signals(price)
    
    if triggered:
        print(f"🔔 {len(triggered)} 个信号触发:")
        for t in triggered:
            sig = t["signal"]
            print(f"   {sig['id']}: {sig['direction'].upper()} @ ${sig['entry_price']:,.0f}")
            print(f"      → {t['status']} @ ${t['closed_price']:,.0f}")
            print(f"      → 结果: {t['result']} ({t['pnl_percent']:+.1f}%)")
    else:
        print(f"当前价格 ${price:,.0f}，无信号触发")


def cmd_list():
    """列出开放信号"""
    signals = load_signals()
    open_sigs = [s for s in signals if s["status"] == "open"]
    
    if not open_sigs:
        print("无开放信号")
        return
    
    print(f"📋 {len(open_sigs)} 个开放信号:")
    for sig in open_sigs:
        print(f"   {sig['id']}: {sig['direction'].upper()} @ ${sig['entry_price']:,.0f}")
        print(f"      SL: ${sig['stop_loss']:,.0f} | TP: ${sig['take_profit_1']:,.0f}")
        print(f"      评分: {sig.get('signal_score', 'N/A')} | {sig['timestamp'][:10]}")


def cmd_close(args):
    """手动关闭信号"""
    if len(args) < 3:
        print("用法: close <signal_id> <result> <closed_price>")
        print("result: win / loss / breakeven")
        return
    
    signal_id = args[0]
    result = args[1]
    closed_price = float(args[2])
    
    # 找到信号并计算 PnL
    signals = load_signals()
    sig = next((s for s in signals if s["id"] == signal_id), None)
    
    if not sig:
        print(f"未找到信号: {signal_id}")
        return
    
    entry = sig["entry_price"]
    if sig["direction"] == "long":
        pnl = (closed_price - entry) / entry * 100
    else:
        pnl = (entry - closed_price) / entry * 100
    
    status = "tp1_hit" if result == "win" else "stopped" if result == "loss" else "cancelled"
    
    update_signal_result(signal_id, status, closed_price, result, round(pnl, 2))
    
    print(f"✅ 已关闭信号: {signal_id}")
    print(f"   结果: {result} ({pnl:+.1f}%)")


def cmd_adjust():
    """调整 Agent 权重"""
    stats = adjust_weights_by_performance()
    print("🔧 权重已根据历史表现调整:")
    for agent in ["derivatives", "technical", "orderflow", "options", "macro", "onchain"]:
        if agent in stats:
            data = stats[agent]
            total = data["correct"] + data["wrong"]
            if total > 0:
                winrate = data["correct"] / total * 100
                print(f"   {agent}: {data['weight']} (胜率 {winrate:.0f}%, {total}次)")
            else:
                print(f"   {agent}: {data['weight']} (无数据)")


def main():
    if len(sys.argv) < 2:
        print("Signal Tracker CLI")
        print("用法:")
        print("  record <direction> <entry> <sl> <tp>  - 记录信号")
        print("  stats                                  - 查看统计")
        print("  check <price>                          - 检查触发")
        print("  list                                   - 列出开放信号")
        print("  close <id> <result> <price>            - 关闭信号")
        print("  adjust                                 - 调整权重")
        return
    
    cmd = sys.argv[1]
    args = sys.argv[2:]
    
    if cmd == "record":
        cmd_record(args)
    elif cmd == "stats":
        cmd_stats()
    elif cmd == "check":
        cmd_check(args)
    elif cmd == "list":
        cmd_list()
    elif cmd == "close":
        cmd_close(args)
    elif cmd == "adjust":
        cmd_adjust()
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
