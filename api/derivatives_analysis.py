#!/usr/bin/env python3
"""
Derivatives Analyst - 衍生品分析脚本
数据源: Binance Futures API + Coinbase Premium
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List


def get_coinbase_premium() -> Dict[str, Any]:
    """获取 Coinbase 溢价"""
    try:
        # Binance price
        resp_b = requests.get("https://fapi.binance.com/fapi/v1/ticker/price", 
                              params={"symbol": "BTCUSDT"}, timeout=10)
        binance_price = float(resp_b.json()["price"])
        
        # Coinbase price
        resp_c = requests.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=10)
        coinbase_price = float(resp_c.json()["data"]["amount"])
        
        premium_pct = (coinbase_price - binance_price) / binance_price * 100
        
        if premium_pct > 0.1:
            signal = "正溢价"
            bias = "bullish"
        elif premium_pct < -0.1:
            signal = "负溢价"
            bias = "bearish"
        else:
            signal = "中性"
            bias = "neutral"
        
        return {
            "binance": round(binance_price, 2),
            "coinbase": round(coinbase_price, 2),
            "premium_pct": round(premium_pct, 4),
            "signal": signal,
            "bias": bias
        }
    except:
        return {"premium_pct": 0, "signal": "N/A", "bias": "neutral"}


class DerivativesAnalyst:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.base_url = "https://fapi.binance.com"
        
    def get_funding_rate(self, limit: int = 8) -> Dict[str, Any]:
        """获取资金费率"""
        url = f"{self.base_url}/fapi/v1/fundingRate"
        params = {"symbol": self.symbol, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if not data:
                return {"error": "No data"}
            
            rates = [float(x["fundingRate"]) for x in data]
            current = rates[0] if rates else 0
            avg = sum(rates) / len(rates) if rates else 0
            
            # 计算连续正/负期数
            consecutive = 0
            direction = "positive" if current >= 0 else "negative"
            for r in rates:
                if (direction == "positive" and r >= 0) or (direction == "negative" and r < 0):
                    consecutive += 1
                else:
                    break
            
            # 信号判断
            if current < -0.03:
                signal = "强烈看多 (极端负费率)"
            elif current < -0.01:
                signal = "看多 (负费率持续)"
            elif current < 0:
                signal = "轻度看多 (负费率)"
            elif current < 0.03:
                signal = "中性"
            elif current < 0.05:
                signal = "轻度看空 (正费率偏高)"
            else:
                signal = "强烈看空 (极端正费率)"
            
            return {
                "current": round(current * 100, 4),  # 转为百分比
                "avg_8": round(avg * 100, 4),
                "trend": direction,
                "consecutive": consecutive,
                "signal": signal,
                "history": [round(r * 100, 4) for r in rates]
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_open_interest(self) -> Dict[str, Any]:
        """获取持仓量"""
        url = f"{self.base_url}/fapi/v1/openInterest"
        params = {"symbol": self.symbol}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            oi = float(data["openInterest"])
            
            # 获取当前价格计算美元价值
            price_resp = requests.get(f"{self.base_url}/fapi/v1/ticker/price", 
                                      params={"symbol": self.symbol}, timeout=10)
            price = float(price_resp.json()["price"])
            oi_usd = oi * price
            
            return {
                "btc": round(oi, 2),
                "usd": round(oi_usd, 0),
                "price": round(price, 2)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_oi_history(self, period: str = "1h", limit: int = 24) -> Dict[str, Any]:
        """获取OI历史变化"""
        url = f"{self.base_url}/futures/data/openInterestHist"
        params = {"symbol": self.symbol, "period": period, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if not data or len(data) < 2:
                return {"error": "Insufficient data"}
            
            latest = float(data[-1]["sumOpenInterestValue"])
            earliest = float(data[0]["sumOpenInterestValue"])
            change_pct = ((latest - earliest) / earliest) * 100 if earliest else 0
            
            # 4小时变化
            if len(data) >= 4:
                four_h_ago = float(data[-5]["sumOpenInterestValue"]) if len(data) >= 5 else earliest
                change_4h_pct = ((latest - four_h_ago) / four_h_ago) * 100 if four_h_ago else 0
            else:
                change_4h_pct = 0
            
            return {
                "latest_usd": round(latest, 0),
                "change_24h_pct": round(change_pct, 2),
                "change_4h_pct": round(change_4h_pct, 2)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_long_short_ratio(self) -> Dict[str, Any]:
        """获取多空比"""
        results = {}
        
        endpoints = {
            "top_accounts": "/futures/data/topLongShortAccountRatio",
            "top_positions": "/futures/data/topLongShortPositionRatio",
            "global": "/futures/data/globalLongShortAccountRatio"
        }
        
        for name, endpoint in endpoints.items():
            try:
                url = f"{self.base_url}{endpoint}"
                params = {"symbol": self.symbol, "period": "1h", "limit": 1}
                resp = requests.get(url, params=params, timeout=10)
                data = resp.json()
                if data:
                    ratio = float(data[0]["longShortRatio"])
                    long_pct = round(ratio / (1 + ratio) * 100, 1)
                    results[name] = {
                        "ratio": round(ratio, 3),
                        "long_pct": long_pct,
                        "short_pct": round(100 - long_pct, 1)
                    }
            except Exception as e:
                results[name] = {"error": str(e)}
        
        # 综合信号
        try:
            avg_long = sum(r.get("long_pct", 50) for r in results.values() if "long_pct" in r) / 3
            if avg_long > 60:
                signal = "大户偏多 (逆向指标: 警惕回调)"
            elif avg_long > 55:
                signal = "略偏多"
            elif avg_long < 40:
                signal = "大户偏空 (逆向指标: 关注反弹)"
            elif avg_long < 45:
                signal = "略偏空"
            else:
                signal = "多空均衡"
            results["signal"] = signal
            results["avg_long_pct"] = round(avg_long, 1)
        except:
            results["signal"] = "数据不足"
        
        return results
    
    def get_taker_ratio(self, limit: int = 24) -> Dict[str, Any]:
        """获取主动买卖比"""
        url = f"{self.base_url}/futures/data/takerlongshortRatio"
        params = {"symbol": self.symbol, "period": "1h", "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if not data:
                return {"error": "No data"}
            
            latest = float(data[-1]["buySellRatio"])
            
            # 计算趋势
            recent_4 = [float(x["buySellRatio"]) for x in data[-4:]]
            avg_4 = sum(recent_4) / len(recent_4)
            
            if latest > 1.1:
                signal = "主动买入强势"
            elif latest > 1.0:
                signal = "买方略占优"
            elif latest > 0.9:
                signal = "卖方略占优"
            else:
                signal = "主动卖出强势"
            
            return {
                "current": round(latest, 3),
                "avg_4h": round(avg_4, 3),
                "signal": signal
            }
        except Exception as e:
            return {"error": str(e)}
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 收集所有数据
        funding = self.get_funding_rate()
        oi_current = self.get_open_interest()
        oi_history = self.get_oi_history()
        long_short = self.get_long_short_ratio()
        taker = self.get_taker_ratio()
        
        # 计算综合倾向
        signals = []
        
        # 资金费率信号
        if "current" in funding:
            if funding["current"] < -0.01:
                signals.append(("bullish", 2))
            elif funding["current"] < 0:
                signals.append(("bullish", 1))
            elif funding["current"] > 0.05:
                signals.append(("bearish", 2))
            elif funding["current"] > 0.03:
                signals.append(("bearish", 1))
        
        # OI 变化信号
        if "change_4h_pct" in oi_history:
            change = oi_history["change_4h_pct"]
            if change > 5:
                signals.append(("neutral", 1))  # OI 快速增加需警惕
            elif change < -5:
                signals.append(("neutral", 1))  # 去杠杆
        
        # 多空比信号 (逆向)
        if "avg_long_pct" in long_short:
            avg = long_short["avg_long_pct"]
            if avg > 60:
                signals.append(("bearish", 1))  # 大户太多看多反而危险
            elif avg < 40:
                signals.append(("bullish", 1))
        
        # Taker 信号
        if "current" in taker:
            if taker["current"] > 1.1:
                signals.append(("bullish", 1))
            elif taker["current"] < 0.9:
                signals.append(("bearish", 1))
        
        # 计算总分
        bull_score = sum(s[1] for s in signals if s[0] == "bullish")
        bear_score = sum(s[1] for s in signals if s[0] == "bearish")
        
        # 更敏感的判断：只要有差异就给出方向
        if bull_score > bear_score:
            bias = "bullish"
            confidence = min(5 + bull_score, 10)
        elif bear_score > bull_score:
            bias = "bearish"
            confidence = min(5 + bear_score, 10)
        else:
            bias = "neutral"
            confidence = 5
        
        # 获取 Coinbase 溢价
        cb_premium = get_coinbase_premium()
        
        # 加入 Coinbase 溢价的 bias
        if cb_premium.get("bias") == "bullish":
            bull_score += 1
        elif cb_premium.get("bias") == "bearish":
            bear_score += 1
        
        # 重新计算 bias (更敏感)
        if bull_score > bear_score:
            bias = "bullish"
            confidence = min(5 + bull_score, 10)
        elif bear_score > bull_score:
            bias = "bearish"
            confidence = min(5 + bear_score, 10)
        else:
            bias = "neutral"
            confidence = 5
        
        # 生成要点
        key_points = []
        if "current" in funding:
            key_points.append(f"资金费率 {funding['current']}% ({'连续' + str(funding['consecutive']) + '期' + funding['trend'] if funding['consecutive'] > 1 else ''})")
        if "change_4h_pct" in oi_history:
            key_points.append(f"OI 4H变化 {oi_history['change_4h_pct']:+.1f}%")
        if "avg_long_pct" in long_short:
            key_points.append(f"大户多空比 {long_short['avg_long_pct']:.0f}% 做多")
        if "current" in taker:
            key_points.append(f"Taker 买卖比 {taker['current']:.2f}")
        if cb_premium.get("premium_pct") is not None:
            key_points.append(f"Coinbase溢价 {cb_premium['premium_pct']:+.3f}% ({cb_premium['signal']})")
        
        return {
            "agent": "derivatives",
            "timestamp": timestamp,
            "symbol": self.symbol,
            "price": oi_current.get("price", 0),
            "bias": bias,
            "confidence": confidence,
            "funding": funding,
            "open_interest": {
                "current": oi_current,
                "history": oi_history
            },
            "long_short_ratio": long_short,
            "taker": taker,
            "key_points": key_points,
            "alerts": [],
            "levels": {
                "resistance": [],
                "support": []
            },
            "coinbase_premium": cb_premium
        }


def main():
    analyst = DerivativesAnalyst("BTCUSDT")
    result = analyst.analyze()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
