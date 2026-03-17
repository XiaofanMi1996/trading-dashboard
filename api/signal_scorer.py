#!/usr/bin/env python3
"""
Signal Scorer - 信号评分系统
将各 Agent 的分析转换为统一的 -10 到 +10 分数
正数 = 看多，负数 = 看空
"""

from typing import Dict, Any

class SignalScorer:
    def __init__(self):
        # 权重配置
        self.weights = {
            "derivatives": 2.5,
            "technical": 2.5,
            "orderflow": 2.0,
            "options": 1.5,
            "macro": 1.0,
            "onchain": 0.5
        }
    
    def score_agent(self, agent_name: str, data: Dict) -> float:
        """为单个 Agent 打分 (-10 到 +10)"""
        if "error" in data or "bias" not in data:
            return 0
        
        bias = data.get("bias", "neutral")
        confidence = data.get("confidence", 5)
        
        # 基础分数
        if bias == "bullish":
            base = 1
        elif bias == "bearish":
            base = -1
        else:
            base = 0
        
        # 信心调整 (1-10 映射到 0.2-1.0)
        confidence_multiplier = 0.2 + (confidence / 10) * 0.8
        
        # 最终分数 (-10 到 +10)
        score = base * confidence * confidence_multiplier
        
        return round(score, 2)
    
    def score_all(self, analyses: Dict[str, Dict]) -> Dict[str, Any]:
        """为所有 Agent 打分并汇总"""
        scores = {}
        weighted_sum = 0
        total_weight = 0
        
        for agent, data in analyses.items():
            if agent in self.weights:
                score = self.score_agent(agent, data)
                weight = self.weights[agent]
                
                scores[agent] = {
                    "score": score,
                    "weight": weight,
                    "weighted_score": round(score * weight / 10, 2)
                }
                
                weighted_sum += score * weight
                total_weight += weight
        
        # 综合分数
        if total_weight > 0:
            final_score = weighted_sum / total_weight
        else:
            final_score = 0
        
        # 解读
        if final_score >= 5:
            interpretation = "强烈看多"
            emoji = "🟢🟢"
        elif final_score >= 2:
            interpretation = "偏多"
            emoji = "🟢"
        elif final_score >= -2:
            interpretation = "中性"
            emoji = "⚪"
        elif final_score >= -5:
            interpretation = "偏空"
            emoji = "🔴"
        else:
            interpretation = "强烈看空"
            emoji = "🔴🔴"
        
        # 分歧检测
        positive = sum(1 for s in scores.values() if s["score"] > 1)
        negative = sum(1 for s in scores.values() if s["score"] < -1)
        has_divergence = positive > 0 and negative > 0
        
        return {
            "scores": scores,
            "final_score": round(final_score, 2),
            "interpretation": interpretation,
            "emoji": emoji,
            "has_divergence": has_divergence,
            "divergence_note": "各分析师有分歧，建议谨慎" if has_divergence else None
        }
    
    def format_scoreboard(self, result: Dict) -> str:
        """格式化评分板"""
        lines = []
        lines.append("📊 信号评分")
        lines.append("")
        
        # 各 Agent 分数
        for agent, data in result["scores"].items():
            score = data["score"]
            if score > 0:
                bar = "+" * min(int(abs(score)), 10)
                display = f"[{bar:>10}]"
            elif score < 0:
                bar = "-" * min(int(abs(score)), 10)
                display = f"[{bar:<10}]"
            else:
                display = "[    ·     ]"
            
            lines.append(f"{agent.capitalize():12} {display} {score:+.1f}")
        
        lines.append("")
        lines.append(f"综合: {result['emoji']} {result['final_score']:+.1f} ({result['interpretation']})")
        
        if result["has_divergence"]:
            lines.append(f"⚠️ {result['divergence_note']}")
        
        return "\n".join(lines)


def main():
    # 测试
    scorer = SignalScorer()
    
    mock_analyses = {
        "derivatives": {"bias": "neutral", "confidence": 5},
        "technical": {"bias": "bearish", "confidence": 8},
        "orderflow": {"bias": "bullish", "confidence": 6},
        "macro": {"bias": "bullish", "confidence": 7},
        "onchain": {"bias": "neutral", "confidence": 5}
    }
    
    result = scorer.score_all(mock_analyses)
    print(scorer.format_scoreboard(result))


if __name__ == "__main__":
    main()
