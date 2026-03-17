#!/usr/bin/env python3
"""
Key Level Alert - 动态关键位预警系统
结合周度框架 + 实时计算 + 6 Agent 验证 + 持仓止盈止损监控 + 历史记录
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple

from signal_history import SignalHistory

class KeyLevelAlert:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.base_dir = os.path.dirname(__file__)
        self.framework_file = os.path.join(self.base_dir, "../data/weekly_framework.json")
        self.state_file = os.path.join(self.base_dir, "../data/key_level_state.json")
        
        # 预警阈值
        self.approach_threshold = 0.02  # 接近关键位 2%
        self.breach_threshold = 0.005   # 突破/跌破 0.5%
        self.tp_approach_threshold = 0.01  # 接近止盈位 1%
        
        # 历史记录
        self.history = SignalHistory()
        
    def load_framework(self) -> Dict:
        """加载周度框架"""
        try:
            with open(self.framework_file, "r") as f:
                return json.load(f)
        except:
            return {}
    
    def load_state(self) -> Dict:
        """加载状态"""
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except:
            return {"alerted_levels": {}, "last_price": 0, "position_alerts": {}}
    
    def save_state(self, state: Dict):
        """保存状态"""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(state, f, indent=2)
    
    def get_price(self) -> float:
        """获取当前价格"""
        url = "https://api.binance.com/api/v3/ticker/price"
        r = requests.get(url, params={"symbol": self.symbol})
        return float(r.json()["price"])
    
    def get_position(self) -> Optional[Dict]:
        """获取 Hyperliquid 持仓"""
        try:
            url = "https://api.hyperliquid.xyz/info"
            payload = {
                "type": "clearinghouseState",
                "user": "0x756434af0362a3437c9b1fc26b5b090a3186377c"
            }
            r = requests.post(url, json=payload)
            data = r.json()
            
            positions = data.get("assetPositions", [])
            for pos in positions:
                position = pos.get("position", {})
                if position.get("coin") == "BTC" and float(position.get("szi", 0)) != 0:
                    size = float(position.get("szi", 0))
                    entry = float(position.get("entryPx", 0))
                    return {
                        "coin": "BTC",
                        "size": size,
                        "direction": "short" if size < 0 else "long",
                        "direction_cn": "空单" if size < 0 else "多单",
                        "entry_price": entry,
                        "abs_size": abs(size)
                    }
            return None
        except:
            return None
    
    def calculate_ema(self, closes: List[float], span: int) -> float:
        """计算 EMA"""
        multiplier = 2 / (span + 1)
        ema = closes[0]
        for price in closes[1:]:
            ema = price * multiplier + ema * (1 - multiplier)
        return ema
    
    def get_dynamic_levels(self) -> Dict[str, List[Dict]]:
        """计算动态关键位"""
        url = "https://api.binance.com/api/v3/klines"
        
        levels = {"resistance": [], "support": []}
        current_price = self.get_price()
        
        timeframes = {
            "4h": {"limit": 350, "emas": [20, 50, 200, 300]},
            "1d": {"limit": 250, "emas": [20, 50, 200]},
            "1w": {"limit": 100, "emas": [20, 50]}
        }
        
        for tf, config in timeframes.items():
            try:
                r = requests.get(url, params={
                    "symbol": self.symbol,
                    "interval": tf,
                    "limit": config["limit"]
                })
                data = r.json()
                closes = [float(k[4]) for k in data]
                highs = [float(k[2]) for k in data]
                lows = [float(k[3]) for k in data]
                
                for ema_period in config["emas"]:
                    if len(closes) >= ema_period:
                        ema_value = self.calculate_ema(closes, ema_period)
                        level = {
                            "price": round(ema_value, 0),
                            "name": f"{tf.upper()} EMA{ema_period}",
                            "type": "ema",
                            "timeframe": tf,
                            "dynamic": True
                        }
                        if ema_value > current_price:
                            levels["resistance"].append(level)
                        else:
                            levels["support"].append(level)
                
                if len(closes) >= 20:
                    sma20 = sum(closes[-20:]) / 20
                    std20 = (sum((c - sma20) ** 2 for c in closes[-20:]) / 20) ** 0.5
                    upper_band = sma20 + 2 * std20
                    lower_band = sma20 - 2 * std20
                    
                    if upper_band > current_price:
                        levels["resistance"].append({
                            "price": round(upper_band, 0),
                            "name": f"{tf.upper()} 布林上轨",
                            "type": "boll",
                            "timeframe": tf,
                            "dynamic": True
                        })
                    if lower_band < current_price:
                        levels["support"].append({
                            "price": round(lower_band, 0),
                            "name": f"{tf.upper()} 布林下轨",
                            "type": "boll",
                            "timeframe": tf,
                            "dynamic": True
                        })
                
                recent_high = max(highs[-20:])
                recent_low = min(lows[-20:])
                
                if recent_high > current_price * 1.005:
                    levels["resistance"].append({
                        "price": round(recent_high, 0),
                        "name": f"{tf.upper()} 近期高点",
                        "type": "swing",
                        "timeframe": tf,
                        "dynamic": True
                    })
                if recent_low < current_price * 0.995:
                    levels["support"].append({
                        "price": round(recent_low, 0),
                        "name": f"{tf.upper()} 近期低点",
                        "type": "swing",
                        "timeframe": tf,
                        "dynamic": True
                    })
                    
            except Exception as e:
                continue
        
        levels["resistance"] = self._dedupe_levels(
            sorted(levels["resistance"], key=lambda x: x["price"])
        )
        levels["support"] = self._dedupe_levels(
            sorted(levels["support"], key=lambda x: x["price"], reverse=True)
        )
        
        return levels
    
    def _dedupe_levels(self, levels: List[Dict], threshold: float = 0.005) -> List[Dict]:
        """去重相近的价位"""
        if not levels:
            return []
        result = [levels[0]]
        for level in levels[1:]:
            if abs(level["price"] - result[-1]["price"]) / result[-1]["price"] > threshold:
                result.append(level)
        return result[:5]
    
    def check_proximity(self, price: float, levels: Dict) -> List[Dict]:
        """检查价格是否接近关键位"""
        alerts = []
        
        for level_type in ["resistance", "support"]:
            for level in levels.get(level_type, []):
                distance = (level["price"] - price) / price
                abs_distance = abs(distance)
                
                if abs_distance <= self.approach_threshold:
                    status = "approaching"
                    if abs_distance <= self.breach_threshold:
                        if level_type == "resistance" and price > level["price"]:
                            status = "breached_up"
                        elif level_type == "support" and price < level["price"]:
                            status = "breached_down"
                        else:
                            status = "at_level"
                    
                    alerts.append({
                        "level": level,
                        "level_type": level_type,
                        "distance_pct": round(distance * 100, 2),
                        "status": status
                    })
        
        return alerts
    
    def _calculate_structural_sl_tp(self, price: float, direction: str, 
                                     levels: Dict, trigger_level: Dict) -> Dict:
        """根据结构计算止盈止损"""
        result = {
            "stop_loss": None,
            "tp1": None,
            "tp2": None,
            "sl_name": "",
            "tp1_name": "",
            "tp2_name": ""
        }
        
        resistances = sorted(levels.get("resistance", []), key=lambda x: x["price"])
        supports = sorted(levels.get("support", []), key=lambda x: x["price"], reverse=True)
        
        if direction == "short":
            # 空单：止损在上方阻力，止盈在下方支撑
            # 找比当前价格高的最近阻力作为止损
            sl_candidates = [r for r in resistances if r["price"] > price]
            if sl_candidates:
                sl_level = sl_candidates[0]
                # 止损设在阻力上方一点点
                result["stop_loss"] = round(sl_level["price"] * 1.002, 0)
                result["sl_name"] = sl_level["name"]
            else:
                # 没有明确阻力，用触发位上方 1%
                result["stop_loss"] = round(trigger_level["price"] * 1.01, 0)
                result["sl_name"] = f"{trigger_level['name']}+1%"
            
            # 找比当前价格低的支撑作为止盈
            tp_candidates = [s for s in supports if s["price"] < price]
            if len(tp_candidates) >= 1:
                result["tp1"] = round(tp_candidates[0]["price"], 0)
                result["tp1_name"] = tp_candidates[0]["name"]
            if len(tp_candidates) >= 2:
                result["tp2"] = round(tp_candidates[1]["price"], 0)
                result["tp2_name"] = tp_candidates[1]["name"]
            
            # 如果没有支撑，用入场价下方 1.5%
            if not result["tp1"]:
                result["tp1"] = round(price * 0.985, 0)
                result["tp1_name"] = "入场-1.5%"
                
        else:  # long
            # 多单：止损在下方支撑，止盈在上方阻力
            # 找比当前价格低的最近支撑作为止损
            sl_candidates = [s for s in supports if s["price"] < price]
            if sl_candidates:
                sl_level = sl_candidates[0]
                # 止损设在支撑下方一点点
                result["stop_loss"] = round(sl_level["price"] * 0.998, 0)
                result["sl_name"] = sl_level["name"]
            else:
                # 没有明确支撑，用触发位下方 1%
                result["stop_loss"] = round(trigger_level["price"] * 0.99, 0)
                result["sl_name"] = f"{trigger_level['name']}-1%"
            
            # 找比当前价格高的阻力作为止盈
            tp_candidates = [r for r in resistances if r["price"] > price]
            if len(tp_candidates) >= 1:
                result["tp1"] = round(tp_candidates[0]["price"], 0)
                result["tp1_name"] = tp_candidates[0]["name"]
            if len(tp_candidates) >= 2:
                result["tp2"] = round(tp_candidates[1]["price"], 0)
                result["tp2_name"] = tp_candidates[1]["name"]
            
            # 如果没有阻力，用入场价上方 1.5%
            if not result["tp1"]:
                result["tp1"] = round(price * 1.015, 0)
                result["tp1_name"] = "入场+1.5%"
        
        return result
    
    def check_candle_confirmation(self, level: Dict, direction: str) -> Dict:
        """检查 K 线确认信号"""
        try:
            url = "https://api.binance.com/api/v3/klines"
            # 检查 15m 和 1h K 线
            confirmations = {}
            
            for tf in ["15m", "1h"]:
                params = {"symbol": self.symbol, "interval": tf, "limit": 3}
                r = requests.get(url, params=params)
                data = r.json()
                
                if len(data) < 2:
                    continue
                
                # 最近两根K线
                prev_candle = data[-2]
                curr_candle = data[-1]
                
                prev_open = float(prev_candle[1])
                prev_close = float(prev_candle[4])
                prev_high = float(prev_candle[2])
                prev_low = float(prev_candle[3])
                
                curr_open = float(curr_candle[1])
                curr_close = float(curr_candle[4])
                curr_high = float(curr_candle[2])
                curr_low = float(curr_candle[3])
                
                level_price = level["price"]
                
                # 检查确认信号
                if direction == "空":
                    # 做空确认：长上影、假突破回落、收阴
                    upper_wick = curr_high - max(curr_open, curr_close)
                    body = abs(curr_close - curr_open)
                    
                    has_long_upper = upper_wick > body * 1.5 if body > 0 else upper_wick > 50
                    is_bearish_close = curr_close < curr_open
                    fake_breakout = prev_high > level_price and curr_close < level_price
                    
                    confirmations[tf] = {
                        "long_upper_wick": has_long_upper,
                        "bearish_close": is_bearish_close,
                        "fake_breakout": fake_breakout,
                        "confirmed": has_long_upper or (is_bearish_close and fake_breakout)
                    }
                else:
                    # 做多确认：长下影、假跌破反弹、收阳
                    lower_wick = min(curr_open, curr_close) - curr_low
                    body = abs(curr_close - curr_open)
                    
                    has_long_lower = lower_wick > body * 1.5 if body > 0 else lower_wick > 50
                    is_bullish_close = curr_close > curr_open
                    fake_breakdown = prev_low < level_price and curr_close > level_price
                    
                    confirmations[tf] = {
                        "long_lower_wick": has_long_lower,
                        "bullish_close": is_bullish_close,
                        "fake_breakdown": fake_breakdown,
                        "confirmed": has_long_lower or (is_bullish_close and fake_breakdown)
                    }
            
            # 综合确认
            any_confirmed = any(c.get("confirmed", False) for c in confirmations.values())
            
            return {
                "confirmations": confirmations,
                "any_confirmed": any_confirmed,
                "description": self._format_confirmation(confirmations, direction)
            }
        except Exception as e:
            return {"error": str(e), "any_confirmed": False, "confirmations": {}}
    
    def _format_confirmation(self, confirmations: Dict, direction: str) -> str:
        """格式化确认信号描述"""
        signals = []
        for tf, conf in confirmations.items():
            if direction == "空":
                if conf.get("long_upper_wick"):
                    signals.append(f"{tf} 长上影")
                if conf.get("fake_breakout"):
                    signals.append(f"{tf} 假突破回落")
                if conf.get("bearish_close"):
                    signals.append(f"{tf} 收阴")
            else:
                if conf.get("long_lower_wick"):
                    signals.append(f"{tf} 长下影")
                if conf.get("fake_breakdown"):
                    signals.append(f"{tf} 假跌破反弹")
                if conf.get("bullish_close"):
                    signals.append(f"{tf} 收阳")
        
        if signals:
            return "、".join(signals[:3])
        return "暂无确认信号"
    
    def get_agent_verification(self, direction: str) -> Dict:
        """获取 6 Agent 验证"""
        try:
            from trading_desk import TradingDesk
            desk = TradingDesk(self.symbol)
            analyses = desk.run_all_analysts()
            synthesis = desk.synthesize(analyses)
            
            votes = {"support": 0, "against": 0, "neutral": 0}
            details = []
            
            expected = "bullish" if direction == "多" else "bearish"
            
            for agent_name, agent_data in synthesis.get("raw_analyses", {}).items():
                agent_direction = agent_data.get("direction", "neutral")
                confidence = agent_data.get("confidence", 5)
                key_points = agent_data.get("key_points", [])[:2]
                
                if agent_direction == expected:
                    votes["support"] += 1
                    emoji = "✅"
                elif agent_direction == "neutral":
                    votes["neutral"] += 1
                    emoji = "⚪"
                else:
                    votes["against"] += 1
                    emoji = "❌"
                
                details.append({
                    "agent": agent_name,
                    "emoji": emoji,
                    "direction": agent_direction,
                    "confidence": confidence,
                    "key_points": key_points
                })
            
            return {
                "votes": votes,
                "details": details,
                "support_ratio": votes["support"] / max(votes["support"] + votes["against"], 1),
                "total_support": votes["support"],
                "total_against": votes["against"]
            }
        except Exception as e:
            return {"error": str(e), "votes": {}, "details": []}
    
    def generate_entry_suggestion(self, framework: Dict, alert: Dict, verification: Dict) -> Dict:
        """生成入场建议"""
        direction = framework.get("direction", "neutral")
        direction_cn = framework.get("direction_cn", "中性")
        level = alert["level"]
        level_type = alert["level_type"]
        status = alert["status"]
        invalidation = framework.get("invalidation", {})
        
        # 检查是否到了变更条件位置
        consider_long_level = invalidation.get("consider_long", "")
        at_reversal_zone = False
        if "62" in consider_long_level or "63" in consider_long_level:
            if level["price"] < 65000:
                at_reversal_zone = True
        
        # 根据大框架和位置类型决定建议方向
        if direction == "bearish":
            if level_type == "resistance":
                suggested_action = "做空"
                suggested_emoji = "🔴"
            elif at_reversal_zone:
                suggested_action = "轻仓做多（逆框架）"
                suggested_emoji = "🟢"
            else:
                suggested_action = "观察反弹做空机会"
                suggested_emoji = "👀"
        elif direction == "bullish":
            if level_type == "support":
                suggested_action = "做多"
                suggested_emoji = "🟢"
            else:
                suggested_action = "观察回调做多机会"
                suggested_emoji = "👀"
        else:
            suggested_action = "观望"
            suggested_emoji = "⚪"
        
        # 根据状态调整建议
        if status == "breached_up" and level_type == "resistance":
            if direction == "bearish":
                action_detail = "突破阻力，观察是否假突破回落"
            else:
                action_detail = "突破确认，可考虑做多"
        elif status == "breached_down" and level_type == "support":
            if direction == "bullish":
                action_detail = "跌破支撑，观察是否假跌破反弹"
            else:
                action_detail = "跌破确认，可考虑做空"
        elif status == "at_level":
            action_detail = "正在测试该位置，等待方向确认"
        else:
            action_detail = f"接近关键位，准备观察"
        
        # 计算止损位
        if "做空" in suggested_action:
            stop_loss = level["price"] * 1.01
        elif "做多" in suggested_action:
            stop_loss = level["price"] * 0.99
        else:
            stop_loss = None
        
        return {
            "type": "entry",
            "suggested_action": suggested_action,
            "suggested_emoji": suggested_emoji,
            "action_detail": action_detail,
            "stop_loss": round(stop_loss, 0) if stop_loss else None,
            "framework_direction": direction_cn,
            "confidence": "高" if verification.get("support_ratio", 0) > 0.6 else "中" if verification.get("support_ratio", 0) > 0.4 else "低"
        }
    
    def generate_position_monitor(self, position: Dict, price: float, levels: Dict) -> Dict:
        """生成持仓监控建议"""
        direction = position["direction"]
        entry_price = position["entry_price"]
        
        # 计算盈亏
        if direction == "short":
            pnl_pct = (entry_price - price) / entry_price * 100
        else:
            pnl_pct = (price - entry_price) / entry_price * 100
        
        pnl_dollar = position["abs_size"] * abs(entry_price - price)
        if (direction == "short" and price > entry_price) or (direction == "long" and price < entry_price):
            pnl_dollar = -pnl_dollar
        
        # 确定止盈止损目标
        if direction == "short":
            # 空单：下方支撑是止盈，上方阻力是止损
            tp_levels = levels.get("support", [])[:3]
            sl_levels = levels.get("resistance", [])[:2]
        else:
            # 多单：上方阻力是止盈，下方支撑是止损
            tp_levels = levels.get("resistance", [])[:3]
            sl_levels = levels.get("support", [])[:2]
        
        # 检查是否接近止盈位
        tp_alerts = []
        for i, tp in enumerate(tp_levels):
            distance = abs(tp["price"] - price) / price
            if distance <= self.tp_approach_threshold:
                tp_alerts.append({
                    "level": tp,
                    "tp_num": i + 1,
                    "distance_pct": round(distance * 100, 2)
                })
        
        # 检查是否接近止损位
        sl_alerts = []
        for sl in sl_levels:
            distance = abs(sl["price"] - price) / price
            if distance <= self.tp_approach_threshold:
                sl_alerts.append({
                    "level": sl,
                    "distance_pct": round(distance * 100, 2)
                })
        
        return {
            "type": "position_monitor",
            "position": position,
            "price": price,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_dollar": round(pnl_dollar, 2),
            "tp_levels": tp_levels,
            "sl_levels": sl_levels,
            "tp_alerts": tp_alerts,
            "sl_alerts": sl_alerts,
            "should_notify": len(tp_alerts) > 0 or len(sl_alerts) > 0
        }
    
    def get_current_zone(self, price: float, framework: Dict) -> Optional[Dict]:
        """检测当前价格所在的交易区间"""
        trade_zones = framework.get("trade_zones", {})
        
        # 检查压力区
        for zone in trade_zones.get("resistance", []):
            if zone["range"][0] <= price <= zone["range"][1]:
                return {"type": "resistance", "zone": zone}
        
        # 检查支撑区
        for zone in trade_zones.get("support", []):
            if zone["range"][0] <= price <= zone["range"][1]:
                return {"type": "support", "zone": zone}
        
        return None
    
    def judge_market_nature(self, verification: Dict, candle_confirm: Dict, 
                            zone_type: str, price_vs_zone: str) -> Dict:
        """判断盘面性质：轧空/砸盘/震荡/趋势"""
        details = verification.get("details", [])
        deriv = next((d for d in details if d["agent"] == "derivatives"), None)
        orderflow = next((d for d in details if d["agent"] == "orderflow"), None)
        
        nature = {"type": "unknown", "description": "", "action_hint": ""}
        
        # 提取关键数据
        funding_negative = False
        oi_increasing = False
        cvd_bullish = False
        has_wick = False
        
        if deriv:
            for p in deriv.get("key_points", []):
                if "negative" in p.lower() or "-0.0" in p:
                    funding_negative = True
                if "+1" in p or "+2" in p or "增" in p:
                    oi_increasing = True
        
        if orderflow:
            for p in orderflow.get("key_points", []):
                if "买" in p and ("5" in p or "6" in p or "7" in p):  # >50% 买方
                    cvd_bullish = True
        
        if candle_confirm:
            desc = candle_confirm.get("description", "")
            if "长上影" in desc or "插针" in desc or "假突破" in desc:
                has_wick = True
        
        # 判断逻辑
        if zone_type == "resistance":
            if funding_negative and oi_increasing and cvd_bullish and not has_wick:
                nature = {
                    "type": "short_squeeze",
                    "description": "🚀 **轧空行情**：空头被逼平仓推高价格",
                    "action_hint": "别急着空，等插针或资金费率转正"
                }
            elif has_wick:
                nature = {
                    "type": "rejection",
                    "description": "🎯 **压力位确认**：插针回落，空头有机会",
                    "action_hint": "可以考虑做空，止损放插针高点上方"
                }
            elif oi_increasing and cvd_bullish:
                nature = {
                    "type": "momentum",
                    "description": "📈 **多头动能强**：有突破可能",
                    "action_hint": "观望为主，等突破失败再空"
                }
            else:
                nature = {
                    "type": "testing",
                    "description": "⏳ **试探压力区**：价格在区间内，但还没出现插针、假突破等明确信号",
                    "action_hint": "暂时观望，等 15min/1H K 线收盘看有没有反转形态"
                }
        
        elif zone_type == "support":
            if funding_negative and not cvd_bullish:
                nature = {
                    "type": "capitulation",
                    "description": "💀 **恐慌抛售**：可能接近底部",
                    "action_hint": "观察止跌信号，别抄飞刀"
                }
            elif has_wick:
                nature = {
                    "type": "support_confirm",
                    "description": "🎯 **支撑位确认**：下影线止跌",
                    "action_hint": "可以考虑轻仓做多"
                }
            else:
                nature = {
                    "type": "testing",
                    "description": "⏳ **试探支撑区**：价格在区间内，但还没出现下影线、止跌等明确信号",
                    "action_hint": "暂时观望，等 15min/1H K 线收盘看有没有止跌形态"
                }
        
        return nature
    
    def analyze_zone_entry(self, price: float, zone: Dict, zone_type: str, 
                           verification: Dict, candle_confirm: Dict, 
                           framework: Dict) -> str:
        """进入交易区间时的完整分析"""
        lines = []
        
        # 标题
        zone_emoji = "🔴" if zone_type == "resistance" else "🟢"
        lines.append(f"{zone_emoji} **进入{zone['name']}** | BTC ${price:,.0f}")
        lines.append(f"区间：${zone['range'][0]:,} - ${zone['range'][1]:,}")
        lines.append("")
        
        # 判断盘面性质
        price_vs_zone = "middle"
        if price > zone["range"][1] * 0.98:
            price_vs_zone = "upper"
        elif price < zone["range"][0] * 1.02:
            price_vs_zone = "lower"
        
        nature = self.judge_market_nature(verification, candle_confirm, zone_type, price_vs_zone)
        lines.append(nature["description"])
        lines.append(f"→ {nature['action_hint']}")
        lines.append("")
        
        # 推动分析
        lines.append("**📊 推动分析：**")
        details = verification.get("details", [])
        
        # 期货 vs 现货
        deriv = next((d for d in details if d["agent"] == "derivatives"), None)
        orderflow = next((d for d in details if d["agent"] == "orderflow"), None)
        
        if deriv:
            oi_info = [p for p in deriv.get("key_points", []) if "OI" in p]
            funding_info = [p for p in deriv.get("key_points", []) if "资金费率" in p or "费率" in p]
            if oi_info:
                lines.append(f"• 期货：{oi_info[0]}")
            if funding_info:
                lines.append(f"• 费率：{funding_info[0]}")
        
        if orderflow:
            cvd_info = [p for p in orderflow.get("key_points", []) if "CVD" in p]
            if cvd_info:
                lines.append(f"• 订单流：{cvd_info[0]}")
        
        # 判断是期货还是现货推动
        if deriv and orderflow:
            deriv_signal = deriv.get("signal", "neutral")
            flow_signal = orderflow.get("signal", "neutral")
            if "OI" in str(deriv.get("key_points", [])) and "+1" in str(deriv.get("key_points", [])):
                lines.append("→ **期货主导**（OI 增加）")
            else:
                lines.append("→ 现货/混合驱动")
        
        lines.append("")
        
        # K 线形态
        lines.append("**📈 形态分析：**")
        if candle_confirm and candle_confirm.get("any_confirmed"):
            lines.append(f"• {candle_confirm.get('description', '')}")
            # 判断是否有插针
            desc = candle_confirm.get('description', '').lower()
            if "长上影" in desc or "插针" in desc or "假突破" in desc:
                lines.append("→ **插针/假突破信号**，压力区有效")
            elif "长下影" in desc:
                lines.append("→ **止跌信号**，支撑区有效")
        else:
            lines.append("• 暂无明确K线信号，等待确认")
        
        lines.append("")
        
        # 操作建议
        lines.append("**💡 操作建议：**")
        direction = framework.get("direction", "neutral")
        
        if zone_type == "resistance":
            if direction == "bearish":
                lines.append(f"✅ **可以做空**（框架主空 + 压力区）")
                lines.append(f"• 建议仓位：{zone.get('position_pct', 20)}%")
                
                # 下一个压力区
                trade_zones = framework.get("trade_zones", {})
                next_resistance = None
                for r in trade_zones.get("resistance", []):
                    if r["range"][0] > zone["range"][1]:
                        next_resistance = r
                        break
                if next_resistance:
                    lines.append(f"• 如果突破：等 ${next_resistance['range'][0]:,}-${next_resistance['range'][1]:,} ({next_resistance['name']})")
                
                # 止盈参考
                supports = trade_zones.get("support", [])
                if supports:
                    lines.append(f"• 止盈参考：${supports[0]['range'][0]:,} ({supports[0]['name']})")
            else:
                lines.append("⚠️ 框架非主空，谨慎做空")
            
            lines.append("")
            lines.append("**如果做多：**")
            lines.append("• 需等回踩支撑区 + 止跌形态")
            lines.append("• 或突破本区间上沿后回踩确认")
            
        elif zone_type == "support":
            if direction == "bullish":
                lines.append(f"✅ **可以做多**（框架主多 + 支撑区）")
                lines.append(f"• 建议仓位：{zone.get('position_pct', 20)}%")
            else:
                lines.append("⚠️ 框架主空，可考虑轻仓做多或空单止盈")
                lines.append(f"• 空单止盈区：{zone['name']}")
            
            lines.append("")
            lines.append("**如果做空：**")
            lines.append("• 需等反弹压力区 + 滞涨形态")
        
        return "\n".join(lines)
    
    def format_entry_alert(self, price: float, alert: Dict, framework: Dict, 
                           verification: Dict, suggestion: Dict, 
                           candle_confirm: Dict = None) -> str:
        """格式化入场预警消息"""
        level = alert["level"]
        
        # 检查是否在框架定义的交易区间内
        current_zone = self.get_current_zone(price, framework)
        
        # 如果在交易区间内，使用完整分析格式
        if current_zone:
            zone = current_zone["zone"]
            zone_type = current_zone["type"]
            
            analysis = self.analyze_zone_entry(
                price, zone, zone_type, 
                verification, candle_confirm, framework
            )
            
            # 添加事件提醒
            events = framework.get("events", [])
            if events:
                upcoming = [e for e in events if e.get("importance") == "high"]
                if upcoming:
                    analysis += f"\n\n⚠️ 注意：{upcoming[0]['name']} ({upcoming[0]['date']})"
            
            return analysis
        
        # 不在交易区间内，使用简化格式
        lines = []
        lines.append(f"📍 **关键位预警** | BTC ${price:,.0f}")
        lines.append("")
        
        lines.append(f"**接近：{level['name']}** (${level['price']:,.0f})")
        lines.append(f"距离：{alert['distance_pct']:+.1f}% | 状态：{self._status_cn(alert['status'])}")
        lines.append(f"大框架：{suggestion['framework_direction']}")
        lines.append("")
        
        lines.append(f"{suggestion['suggested_emoji']} **建议：{suggestion['suggested_action']}**")
        lines.append(f"→ {suggestion['action_detail']}")
        if suggestion['stop_loss']:
            lines.append(f"→ 止损参考：${suggestion['stop_loss']:,.0f}")
        
        # K 线确认信号
        if candle_confirm and candle_confirm.get("any_confirmed"):
            lines.append(f"✅ K线确认：{candle_confirm.get('description', '')}")
        elif candle_confirm:
            lines.append(f"⏳ 待确认：{candle_confirm.get('description', '等待K线信号')}")
        lines.append("")
        
        lines.append("**6 Agent 验证：**")
        for detail in verification.get("details", []):
            key_info = detail["key_points"][0] if detail["key_points"] else ""
            lines.append(f"{detail['emoji']} {detail['agent']}: {key_info[:30]}")
        
        votes = verification.get("votes", {})
        lines.append("")
        lines.append(f"**综合：{votes.get('support', 0)}/6 支持{suggestion['suggested_action']}** (置信度：{suggestion['confidence']})")
        
        events = framework.get("events", [])
        if events:
            upcoming = [e for e in events if e.get("importance") == "high"]
            if upcoming:
                lines.append("")
                lines.append(f"⚠️ 注意：{upcoming[0]['name']} ({upcoming[0]['date']})")
        
        return "\n".join(lines)
    
    def format_position_alert(self, monitor: Dict) -> str:
        """格式化持仓监控消息"""
        position = monitor["position"]
        price = monitor["price"]
        
        pnl_emoji = "✅" if monitor["pnl_dollar"] >= 0 else "❌"
        
        lines = []
        lines.append(f"📊 **持仓监控** | BTC {position['direction_cn']} @ ${position['entry_price']:,.0f}")
        lines.append("")
        lines.append(f"当前价：${price:,.0f} | {pnl_emoji} 浮盈 ${monitor['pnl_dollar']:+,.0f} ({monitor['pnl_pct']:+.1f}%)")
        lines.append("")
        
        # 止盈目标
        lines.append("🎯 **止盈目标：**")
        for i, tp in enumerate(monitor["tp_levels"]):
            distance = (tp["price"] - price) / price * 100
            approaching = "← 接近!" if any(a["tp_num"] == i+1 for a in monitor["tp_alerts"]) else ""
            lines.append(f"• TP{i+1}: ${tp['price']:,.0f} ({tp['name']}) — {distance:+.1f}% {approaching}")
        
        lines.append("")
        
        # 止损参考
        lines.append("🛑 **止损参考：**")
        for sl in monitor["sl_levels"]:
            distance = (sl["price"] - price) / price * 100
            warning = "⚠️ 注意!" if any(a["level"]["price"] == sl["price"] for a in monitor["sl_alerts"]) else ""
            lines.append(f"• ${sl['price']:,.0f} ({sl['name']}) — {distance:+.1f}% {warning}")
        
        # 建议
        lines.append("")
        if monitor["tp_alerts"]:
            tp_alert = monitor["tp_alerts"][0]
            lines.append(f"💡 **快到 TP{tp_alert['tp_num']} 了，考虑减仓**")
            if tp_alert["tp_num"] == 1:
                lines.append("→ 建议：平一半，移动止损到成本")
        elif monitor["sl_alerts"]:
            lines.append("⚠️ **接近止损位，注意风险！**")
        
        return "\n".join(lines)
    
    def _status_cn(self, status: str) -> str:
        """状态中文"""
        mapping = {
            "approaching": "接近中",
            "at_level": "测试中",
            "breached_up": "向上突破",
            "breached_down": "向下跌破"
        }
        return mapping.get(status, status)
    
    def run(self) -> Dict[str, Any]:
        """运行检查"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        framework = self.load_framework()
        state = self.load_state()
        
        if not framework:
            return {"timestamp": timestamp, "error": "No framework loaded"}
        
        price = self.get_price()
        position = self.get_position()
        
        # 合并固定关键位和动态关键位
        dynamic_levels = self.get_dynamic_levels()
        
        # 从 trade_zones 提取压力/支撑区
        trade_zones = framework.get("trade_zones", {})
        framework_levels = {"resistance": [], "support": []}
        
        for zone in trade_zones.get("resistance", []):
            framework_levels["resistance"].append({
                "price": zone["range"][1],  # 用区间上限作为关键位
                "price_low": zone["range"][0],
                "name": zone["name"],
                "type": "zone",
                "action": zone.get("action", ""),
                "position_pct": zone.get("position_pct", 0),
                "notes": zone.get("notes", "")
            })
        
        for zone in trade_zones.get("support", []):
            framework_levels["support"].append({
                "price": zone["range"][0],  # 用区间下限作为关键位
                "price_high": zone["range"][1],
                "name": zone["name"],
                "type": "zone",
                "action": zone.get("action", ""),
                "notes": zone.get("notes", "")
            })
        
        all_levels = {
            "resistance": framework_levels.get("resistance", []) + dynamic_levels.get("resistance", []),
            "support": framework_levels.get("support", []) + dynamic_levels.get("support", [])
        }
        
        all_levels["resistance"] = self._dedupe_levels(
            sorted(all_levels["resistance"], key=lambda x: x["price"])
        )
        all_levels["support"] = self._dedupe_levels(
            sorted(all_levels["support"], key=lambda x: x["price"], reverse=True)
        )
        
        result = {
            "timestamp": timestamp,
            "price": price,
            "position": position,
            "framework_direction": framework.get("direction_cn", ""),
            "levels": all_levels,
            "entry_alerts": [],
            "position_alerts": [],
            "sim_closed": [],
            "should_notify": False
        }
        
        # 检查模拟仓位是否触发止盈止损
        sim_closed = self.history.check_and_close_signals(price)
        if sim_closed:
            result["sim_closed"] = sim_closed
            result["should_notify"] = True
        
        # 如果有持仓，优先做持仓监控
        if position:
            monitor = self.generate_position_monitor(position, price, all_levels)
            
            if monitor["should_notify"]:
                # 检查是否已经通知过
                alert_key = f"position_{position['direction']}_{monitor['tp_alerts'][0]['tp_num'] if monitor['tp_alerts'] else 'sl'}"
                last_alert_time = state.get("position_alerts", {}).get(alert_key, 0)
                now = datetime.now(timezone.utc).timestamp()
                
                if now - last_alert_time > 1800:  # 30分钟内不重复
                    message = self.format_position_alert(monitor)
                    result["position_alerts"].append({
                        "monitor": monitor,
                        "message": message
                    })
                    state.setdefault("position_alerts", {})[alert_key] = now
                    result["should_notify"] = True
            
            # 同时也返回持仓状态（不一定通知）
            result["position_monitor"] = monitor
        
        # 检查入场机会
        proximity_alerts = self.check_proximity(price, all_levels)
        
        if proximity_alerts:
            direction_for_verify = "空" if framework.get("direction") == "bearish" else "多"
            verification = self.get_agent_verification(direction_for_verify)
            
            for alert in proximity_alerts:
                level_key = f"{alert['level']['name']}_{alert['status']}"
                last_alert_time = state.get("alerted_levels", {}).get(level_key, 0)
                now = datetime.now(timezone.utc).timestamp()
                
                if now - last_alert_time < 3600:
                    continue
                
                suggestion = self.generate_entry_suggestion(framework, alert, verification)
                
                # 获取 K 线确认信号
                direction_cn = "空" if "空" in suggestion["suggested_action"] else "多"
                candle_confirm = self.check_candle_confirmation(alert["level"], direction_cn)
                
                message = self.format_entry_alert(price, alert, framework, verification, suggestion, candle_confirm)
                
                # 计算结构化止盈止损
                direction = "short" if "空" in suggestion["suggested_action"] else "long"
                sl_tp = self._calculate_structural_sl_tp(price, direction, all_levels, alert["level"])
                
                # 记录到历史
                signal_data = {
                    "timestamp": timestamp,
                    "price": price,
                    "type": "entry",
                    "direction": direction,
                    "level_name": alert["level"]["name"],
                    "level_price": alert["level"]["price"],
                    "suggestion": suggestion["suggested_action"],
                    "agent_votes": {d["agent"]: d["direction"] for d in verification.get("details", [])},
                    "confidence": suggestion["confidence"],
                    "framework_direction": suggestion["framework_direction"],
                    "candle_confirmed": candle_confirm.get("any_confirmed", False),
                    "sim_entry": price,
                    "sim_sl": sl_tp["stop_loss"],
                    "sim_tp1": sl_tp["tp1"],
                    "sim_tp2": sl_tp.get("tp2"),
                    "sl_name": sl_tp["sl_name"],
                    "tp1_name": sl_tp["tp1_name"]
                }
                signal_id = self.history.record_signal(signal_data)
                
                result["entry_alerts"].append({
                    "alert": alert,
                    "verification": verification,
                    "candle_confirm": candle_confirm,
                    "signal_id": signal_id,
                    "suggestion": suggestion,
                    "message": message
                })
                
                state.setdefault("alerted_levels", {})[level_key] = now
                result["should_notify"] = True
        
        state["last_price"] = price
        self.save_state(state)
        
        return result


def main():
    alert_system = KeyLevelAlert()
    result = alert_system.run()
    
    print(json.dumps({
        "timestamp": result["timestamp"],
        "price": result["price"],
        "position": result.get("position"),
        "framework_direction": result["framework_direction"],
        "num_entry_alerts": len(result["entry_alerts"]),
        "num_position_alerts": len(result["position_alerts"]),
        "should_notify": result["should_notify"]
    }, indent=2, ensure_ascii=False))
    
    # 打印持仓监控（如果有）
    if result.get("position_monitor"):
        print("\n" + "=" * 50)
        print("📊 持仓状态：")
        monitor = result["position_monitor"]
        print(f"  方向: {monitor['position']['direction_cn']}")
        print(f"  入场: ${monitor['position']['entry_price']:,.0f}")
        print(f"  当前: ${monitor['price']:,.0f}")
        print(f"  盈亏: ${monitor['pnl_dollar']:+,.0f} ({monitor['pnl_pct']:+.1f}%)")
    
    # 打印模拟仓位平仓结果
    for sim in result.get("sim_closed", []):
        print("\n" + "=" * 50)
        sig = sim["signal"]
        emoji = "✅" if sim["result"] == "win" else "❌"
        print(f"{emoji} 模拟仓位平仓：{sig['direction']} @ {sig['level_name']}")
        print(f"   入场: ${sim['entry']:,.0f} → 平仓: ${sim['closed_price']:,.0f}")
        print(f"   盈亏: {sim['pnl_percent']:+.2f}%")
    
    # 打印预警消息
    for alert_data in result.get("position_alerts", []):
        print("\n" + "=" * 50)
        print(alert_data["message"])
    
    for alert_data in result.get("entry_alerts", []):
        print("\n" + "=" * 50)
        print(alert_data["message"])


if __name__ == "__main__":
    main()
