#!/usr/bin/env python3
"""
Divergence Analyzer - 交叉矛盾分析模块
分析各 Agent 之间的分歧，给出解读
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple


class DivergenceAnalyzer:
    """分析各 Agent 之间的矛盾和分歧"""
    
    def __init__(self):
        # Agent 优先级 (短线交易)
        self.priority = {
            "derivatives": 1,  # 最高
            "technical": 2,
            "orderflow": 3,
            "options": 4,
            "macro": 5,
            "onchain": 6  # 最低
        }
        
        # 常见矛盾模式及解读
        self.conflict_patterns = {
            ("technical", "bearish", "macro", "bullish"): {
                "name": "技术空 vs 情绪多",
                "interpretation": "短期技术面压制，但恐慌情绪是逆向指标。可能是假跌，等反弹确认。",
                "action": "观望，等技术面企稳再考虑做多"
            },
            ("technical", "bullish", "macro", "bearish"): {
                "name": "技术多 vs 情绪空",
                "interpretation": "技术面看涨但市场情绪过热，小心回调。",
                "action": "轻仓或减仓，提高止损"
            },
            ("derivatives", "bullish", "orderflow", "bearish"): {
                "name": "衍生品多 vs 订单流空",
                "interpretation": "杠杆资金看多，但现货在出货。警惕诱多。",
                "action": "不追多，等订单流转正"
            },
            ("derivatives", "bearish", "orderflow", "bullish"): {
                "name": "衍生品空 vs 订单流多",
                "interpretation": "杠杆在减仓，但现货有买盘。可能是洗盘后的积累。",
                "action": "观察，若技术面企稳可轻仓试多"
            },
            ("technical", "bearish", "options", "bullish"): {
                "name": "技术空 vs 期权多",
                "interpretation": "短期下跌，但 Max Pain 在上方。到期前可能有向上修复。",
                "action": "短空长多，注意期权到期日"
            },
            ("orderflow", "bearish", "macro", "bullish"): {
                "name": "订单流空 vs 宏观多",
                "interpretation": "短期卖压，但宏观恐慌是底部信号。可能是最后一跌。",
                "action": "不追空，准备抄底"
            },
        }
    
    def get_biases(self, raw_analyses: Dict) -> Dict[str, str]:
        """提取各 Agent 的方向判断"""
        biases = {}
        for agent, data in raw_analyses.items():
            if isinstance(data, dict) and "bias" in data:
                biases[agent] = data["bias"]
        return biases
    
    def find_conflicts(self, biases: Dict[str, str]) -> List[Dict]:
        """找出所有矛盾对"""
        conflicts = []
        agents = list(biases.keys())
        
        for i, agent1 in enumerate(agents):
            for agent2 in agents[i+1:]:
                bias1 = biases[agent1]
                bias2 = biases[agent2]
                
                # 只关注明确对立 (bullish vs bearish)
                if (bias1 == "bullish" and bias2 == "bearish") or \
                   (bias1 == "bearish" and bias2 == "bullish"):
                    
                    # 按优先级排序
                    if self.priority.get(agent1, 99) < self.priority.get(agent2, 99):
                        higher, lower = agent1, agent2
                        higher_bias, lower_bias = bias1, bias2
                    else:
                        higher, lower = agent2, agent1
                        higher_bias, lower_bias = bias2, bias1
                    
                    conflicts.append({
                        "agents": (higher, lower),
                        "biases": (higher_bias, lower_bias),
                        "higher_priority": higher,
                        "conflict_key": (higher, higher_bias, lower, lower_bias)
                    })
        
        return conflicts
    
    def interpret_conflict(self, conflict: Dict) -> Dict[str, Any]:
        """解读单个矛盾"""
        key = conflict["conflict_key"]
        higher = conflict["higher_priority"]
        agents = conflict["agents"]
        biases = conflict["biases"]
        
        # 查找预设模式
        pattern = self.conflict_patterns.get(key)
        
        if pattern:
            return {
                "conflict": f"{agents[0]}({biases[0]}) vs {agents[1]}({biases[1]})",
                "name": pattern["name"],
                "interpretation": pattern["interpretation"],
                "action": pattern["action"],
                "follow": higher  # 建议跟随哪个
            }
        else:
            # 默认解读：跟随优先级高的
            higher_cn = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}
            return {
                "conflict": f"{agents[0]}({biases[0]}) vs {agents[1]}({biases[1]})",
                "name": f"{agents[0]} vs {agents[1]} 分歧",
                "interpretation": f"{agents[0]} 优先级更高，建议参考其判断",
                "action": f"偏向 {higher_cn.get(biases[0], biases[0])}，但保持谨慎",
                "follow": higher
            }
    
    def analyze_divergence_severity(self, biases: Dict[str, str]) -> Tuple[str, int]:
        """评估分歧严重程度"""
        bullish_count = sum(1 for b in biases.values() if b == "bullish")
        bearish_count = sum(1 for b in biases.values() if b == "bearish")
        neutral_count = sum(1 for b in biases.values() if b == "neutral")
        total = len(biases)
        
        # 计算共识度
        max_count = max(bullish_count, bearish_count, neutral_count)
        consensus = max_count / total if total else 0
        
        if consensus >= 0.8:
            severity = "低"
            severity_score = 1
        elif consensus >= 0.6:
            severity = "中"
            severity_score = 2
        elif consensus >= 0.4:
            severity = "高"
            severity_score = 3
        else:
            severity = "极高"
            severity_score = 4
        
        return severity, severity_score
    
    def get_weighted_direction(self, biases: Dict[str, str], raw_analyses: Dict) -> Dict:
        """根据权重和置信度计算加权方向"""
        weights = {
            "derivatives": 2.5,
            "technical": 2.5,
            "orderflow": 2.0,
            "options": 1.5,
            "macro": 1.0,
            "onchain": 0.5
        }
        
        score = 0
        total_weight = 0
        
        for agent, bias in biases.items():
            weight = weights.get(agent, 1.0)
            confidence = raw_analyses.get(agent, {}).get("confidence", 5) / 10
            
            if bias == "bullish":
                score += weight * confidence
            elif bias == "bearish":
                score -= weight * confidence
            
            total_weight += weight
        
        weighted_score = score / total_weight if total_weight else 0
        
        if weighted_score > 0.2:
            direction = "bullish"
        elif weighted_score < -0.2:
            direction = "bearish"
        else:
            direction = "neutral"
        
        return {
            "weighted_score": round(weighted_score, 2),
            "direction": direction,
            "confidence": abs(weighted_score)
        }
    
    def analyze(self, raw_analyses: Dict) -> Dict[str, Any]:
        """完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 提取各 Agent 方向
        biases = self.get_biases(raw_analyses)
        
        # 找出矛盾
        conflicts = self.find_conflicts(biases)
        
        # 解读每个矛盾
        interpretations = [self.interpret_conflict(c) for c in conflicts]
        
        # 评估分歧严重程度
        severity, severity_score = self.analyze_divergence_severity(biases)
        
        # 加权方向
        weighted = self.get_weighted_direction(biases, raw_analyses)
        
        # 综合建议
        if severity_score >= 3:
            recommendation = "分歧严重，强烈建议观望"
        elif severity_score == 2:
            recommendation = f"有分歧，谨慎操作，倾向{weighted['direction']}"
        else:
            recommendation = f"共识度高，可按信号操作"
        
        return {
            "timestamp": timestamp,
            "biases": biases,
            "conflict_count": len(conflicts),
            "conflicts": interpretations,
            "severity": severity,
            "severity_score": severity_score,
            "weighted_direction": weighted,
            "recommendation": recommendation
        }
    
    def format_report(self, analysis: Dict) -> str:
        """格式化报告"""
        lines = []
        lines.append("🔀 **交叉矛盾分析**")
        lines.append("")
        
        # 各 Agent 观点
        lines.append("**各 Agent 观点:**")
        emoji_map = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}
        for agent, bias in analysis["biases"].items():
            lines.append(f"  {emoji_map.get(bias, '⚪')} {agent}: {bias}")
        
        lines.append("")
        lines.append(f"**分歧程度:** {analysis['severity']} ({analysis['conflict_count']} 对矛盾)")
        
        # 详细矛盾解读
        if analysis["conflicts"]:
            lines.append("")
            lines.append("**矛盾解读:**")
            for i, conflict in enumerate(analysis["conflicts"], 1):
                lines.append(f"\n{i}. **{conflict['name']}**")
                lines.append(f"   {conflict['conflict']}")
                lines.append(f"   解读: {conflict['interpretation']}")
                lines.append(f"   建议: {conflict['action']}")
        
        lines.append("")
        lines.append(f"**加权方向:** {analysis['weighted_direction']['direction']} (置信度 {analysis['weighted_direction']['confidence']:.0%})")
        lines.append(f"**综合建议:** {analysis['recommendation']}")
        
        return "\n".join(lines)


def main():
    # 测试数据
    test_analyses = {
        "derivatives": {"bias": "neutral", "confidence": 5},
        "technical": {"bias": "bearish", "confidence": 8},
        "orderflow": {"bias": "bearish", "confidence": 7},
        "options": {"bias": "neutral", "confidence": 5},
        "macro": {"bias": "bullish", "confidence": 7},
        "onchain": {"bias": "neutral", "confidence": 5}
    }
    
    analyzer = DivergenceAnalyzer()
    result = analyzer.analyze(test_analyses)
    
    print(analyzer.format_report(result))
    print("\n" + "="*50 + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
