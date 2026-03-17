#!/usr/bin/env python3
"""
Trading Desk - 交易分析汇总系统
汇总各 Agent 分析结果，生成统一报告
"""

import json
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# 导入各分析模块
from derivatives_analysis import DerivativesAnalyst
from technical_analysis import TechnicalAnalyst
from macro_analysis import MacroAnalyst
from orderflow_analysis import OrderFlowAnalyst
from onchain_analysis import OnchainAnalyst
from options_analysis import OptionsAnalyst
from signal_scorer import SignalScorer
from history_recorder import HistoryRecorder
from divergence_analyzer import DivergenceAnalyzer
from coinbase_premium import get_coinbase_premium, get_premium_emoji


class TradingDesk:
    def run_all_analysts(self) -> Dict[str, Dict]:
        """运行所有分析师"""
        results = {}
        for name, analyst in self.analysts.items():
            try:
                results[name] = analyst.analyze()
            except Exception as e:
                results[name] = {"error": str(e)}
        return results
    
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.analysts = {
            "derivatives": DerivativesAnalyst(symbol),
            "technical": TechnicalAnalyst(symbol),
            "orderflow": OrderFlowAnalyst(symbol),
            "options": OptionsAnalyst(symbol.replace("USDT", "")),
            "macro": MacroAnalyst(),
            "onchain": OnchainAnalyst()
        }
        # 权重配置 (短线交易优先衍生品、技术、订单流)
        self.weights = {
            "derivatives": 2.0,
            "technical": 2.0,
            "orderflow": 1.5,
            "options": 1.0,
            "macro": 1.0,
            "onchain": 0.5  # 链上数据目前有限，权重低
        }
        self.scorer = SignalScorer()
        self.recorder = HistoryRecorder()
        self.divergence = DivergenceAnalyzer()
    
    def synthesize(self, analyses: Dict[str, Dict]) -> Dict[str, Any]:
        """综合各分析师结果"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 收集各方倾向
        votes = {"bullish": 0, "bearish": 0, "neutral": 0}
        all_key_points = []
        all_alerts = []
        confidences = []
        
        for name, data in analyses.items():
            if "error" in data:
                continue
            
            bias = data.get("bias", "neutral")
            confidence = data.get("confidence", 5)
            weight = self.weights.get(name, 1.0)
            
            votes[bias] += weight * confidence
            confidences.append(confidence)
            
            # 收集要点
            key_points = data.get("key_points", [])
            for kp in key_points[:3]:  # 每个分析师最多3个要点
                all_key_points.append(f"[{name.upper()}] {kp}")
            
            # 收集警报
            alerts = data.get("alerts", [])
            all_alerts.extend(alerts)
        
        # 确定综合倾向 (更敏感)
        if votes["bullish"] > votes["bearish"]:
            final_bias = "bullish"
        elif votes["bearish"] > votes["bullish"]:
            final_bias = "bearish"
        else:
            final_bias = "neutral"
        
        # 综合置信度
        avg_confidence = sum(confidences) / len(confidences) if confidences else 5
        
        # 检查分歧
        biases = [d.get("bias") for d in analyses.values() if "bias" in d]
        has_divergence = len(set(biases)) > 1 and "bullish" in biases and "bearish" in biases
        
        # 生成建议
        if final_bias == "bullish" and avg_confidence >= 7:
            action = "寻找做多机会"
        elif final_bias == "bearish" and avg_confidence >= 7:
            action = "寻找做空机会"
        elif has_divergence:
            action = "分析师有分歧，建议观望"
        else:
            action = "方向不明确，建议观望"
        
        # 价格和关键位
        price = analyses.get("technical", {}).get("price", 0)
        key_levels = analyses.get("technical", {}).get("key_levels", {})
        
        # 信号评分
        score_result = self.scorer.score_all(analyses)
        
        # 交叉矛盾分析
        divergence_result = self.divergence.analyze(analyses)
        
        # Coinbase 溢价 (六维分析之一)
        coinbase_premium = get_coinbase_premium()
        
        return {
            "timestamp": timestamp,
            "symbol": self.symbol,
            "price": price,
            "synthesis": {
                "bias": final_bias,
                "confidence": round(avg_confidence, 1),
                "action": action,
                "divergence": has_divergence
            },
            "signal_score": score_result,
            "coinbase_premium": coinbase_premium,
            "divergence_analysis": divergence_result,
            "votes": {k: round(v, 1) for k, v in votes.items()},
            "individual_biases": {
                name: data.get("bias", "unknown") 
                for name, data in analyses.items() if "bias" in data
            },
            "key_levels": key_levels,
            "key_points": all_key_points,
            "alerts": all_alerts,
            "raw_analyses": analyses
        }
    
    def generate_report(self, synthesis: Dict[str, Any]) -> str:
        """生成人类可读报告"""
        lines = []
        
        # 标题
        lines.append("=" * 50)
        lines.append(f"📊 TRADING DESK REPORT | {self.symbol}")
        lines.append(f"⏰ {synthesis['timestamp']}")
        lines.append(f"💵 Price: ${synthesis['price']:,.2f}")
        lines.append("=" * 50)
        
        # 综合判断
        syn = synthesis["synthesis"]
        bias_emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
        
        lines.append("")
        lines.append("【综合判断】")
        lines.append(f"{bias_emoji.get(syn['bias'], '⚪')} 方向: {syn['bias'].upper()}")
        lines.append(f"📈 置信度: {syn['confidence']}/10")
        
        # 信号评分
        score = synthesis.get("signal_score", {})
        if score:
            lines.append(f"📊 信号分: {score.get('emoji', '')} {score.get('final_score', 0):+.1f} ({score.get('interpretation', '')})")
        
        # Coinbase 溢价
        cb_premium = synthesis.get("coinbase_premium", {})
        if cb_premium and "premium_pct" in cb_premium:
            premium_emoji = get_premium_emoji(cb_premium.get("signal", "neutral"))
            lines.append(f"💵 Coinbase溢价: {premium_emoji} {cb_premium['premium_pct']:+.3f}%")
        
        lines.append(f"🎯 建议: {syn['action']}")
        
        if syn["divergence"]:
            lines.append("⚠️ 注意: 各分析师有分歧")
        
        # 各方投票
        lines.append("")
        lines.append("【各分析师观点】")
        for name, bias in synthesis["individual_biases"].items():
            emoji = bias_emoji.get(bias, "⚪")
            lines.append(f"  {emoji} {name.capitalize()}: {bias}")
        
        # 关键位
        levels = synthesis.get("key_levels", {})
        if levels:
            lines.append("")
            lines.append("【关键价位】")
            if levels.get("resistance"):
                lines.append(f"  压力: {', '.join(f'${r:,.0f}' for r in levels['resistance'][:3])}")
            if levels.get("support"):
                lines.append(f"  支撑: {', '.join(f'${s:,.0f}' for s in levels['support'][:3])}")
        
        # 要点
        if synthesis.get("key_points"):
            lines.append("")
            lines.append("【关键要点】")
            for kp in synthesis["key_points"][:8]:
                lines.append(f"  • {kp}")
        
        # 警报
        if synthesis.get("alerts"):
            lines.append("")
            lines.append("【⚠️ 警报】")
            for alert in synthesis["alerts"]:
                lines.append(f"  {alert}")
        
        lines.append("")
        lines.append("=" * 50)
        
        return "\n".join(lines)
    
    def run(self, output_format: str = "report", trigger: str = "manual", save: bool = True) -> str:
        """运行完整分析流程"""
        # 运行所有分析师
        analyses = self.run_all_analysts()
        
        # 综合结果
        synthesis = self.synthesize(analyses)
        
        # 保存历史记录
        if save:
            record_id = self.recorder.save_analysis(synthesis, trigger=trigger)
            synthesis["record_id"] = record_id
        
        if output_format == "json":
            return json.dumps(synthesis, indent=2, ensure_ascii=False)
        else:
            return self.generate_report(synthesis)


def main():
    output_format = sys.argv[1] if len(sys.argv) > 1 else "report"
    
    desk = TradingDesk("BTCUSDT")
    result = desk.run(output_format)
    print(result)


if __name__ == "__main__":
    main()
