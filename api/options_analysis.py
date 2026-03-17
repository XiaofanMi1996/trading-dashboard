#!/usr/bin/env python3
"""
Options Analyst - 期权分析脚本
数据源: Deribit API (免费)
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

class OptionsAnalyst:
    def __init__(self, currency: str = "BTC"):
        self.currency = currency
        self.base_url = "https://www.deribit.com/api/v2/public"
    
    def get_index_price(self) -> float:
        """获取指数价格"""
        url = f"{self.base_url}/get_index_price"
        params = {"index_name": f"{self.currency.lower()}_usd"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return data.get("result", {}).get("index_price", 0)
        except:
            return 0
    
    def get_book_summary(self) -> Dict[str, Any]:
        """获取期权市场汇总"""
        url = f"{self.base_url}/get_book_summary_by_currency"
        params = {"currency": self.currency, "kind": "option"}
        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            return data.get("result", [])
        except Exception as e:
            return []
    
    def get_historical_volatility(self) -> Dict[str, Any]:
        """获取历史波动率"""
        url = f"{self.base_url}/get_historical_volatility"
        params = {"currency": self.currency}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            result = data.get("result", [])
            if result:
                # 返回最近的 HV
                latest = result[-1] if result else [0, 0]
                return {
                    "hv_30d": round(latest[1] * 100, 2) if len(latest) > 1 else 0
                }
        except:
            pass
        return {"hv_30d": 0}
    
    def analyze_pcr(self, book_summary: List) -> Dict[str, Any]:
        """计算 Put/Call Ratio"""
        if not book_summary:
            return {"error": "No data"}
        
        call_volume = 0
        put_volume = 0
        call_oi = 0
        put_oi = 0
        
        for item in book_summary:
            instrument = item.get("instrument_name", "")
            if "-C" in instrument:
                call_volume += item.get("volume", 0)
                call_oi += item.get("open_interest", 0)
            elif "-P" in instrument:
                put_volume += item.get("volume", 0)
                put_oi += item.get("open_interest", 0)
        
        # PCR 计算
        pcr_volume = put_volume / call_volume if call_volume else 0
        pcr_oi = put_oi / call_oi if call_oi else 0
        
        # 信号判断
        # PCR > 1 = 看跌情绪浓 (逆向看多)
        # PCR < 0.7 = 看涨情绪浓 (逆向看空)
        if pcr_oi > 1.2:
            signal = "极度看跌 (逆向看多)"
            impact = "bullish"
        elif pcr_oi > 0.9:
            signal = "偏看跌"
            impact = "neutral"
        elif pcr_oi > 0.7:
            signal = "均衡"
            impact = "neutral"
        elif pcr_oi > 0.5:
            signal = "偏看涨"
            impact = "neutral"
        else:
            signal = "极度看涨 (逆向看空)"
            impact = "bearish"
        
        return {
            "pcr_volume": round(pcr_volume, 3),
            "pcr_oi": round(pcr_oi, 3),
            "call_oi": round(call_oi, 0),
            "put_oi": round(put_oi, 0),
            "signal": signal,
            "impact": impact
        }
    
    def analyze_max_pain(self, book_summary: List, current_price: float) -> Dict[str, Any]:
        """计算 Max Pain (简化版)"""
        if not book_summary or not current_price:
            return {"error": "No data"}
        
        # 收集所有 strike 的 OI
        strikes = {}
        
        for item in book_summary:
            instrument = item.get("instrument_name", "")
            oi = item.get("open_interest", 0)
            
            # 解析 strike: BTC-28MAR26-70000-C
            parts = instrument.split("-")
            if len(parts) >= 4:
                try:
                    strike = int(parts[2])
                    opt_type = parts[3]  # C or P
                    
                    if strike not in strikes:
                        strikes[strike] = {"call_oi": 0, "put_oi": 0}
                    
                    if opt_type == "C":
                        strikes[strike]["call_oi"] += oi
                    else:
                        strikes[strike]["put_oi"] += oi
                except:
                    pass
        
        if not strikes:
            return {"error": "No strikes found"}
        
        # 简化 Max Pain: OI 最大的 strike
        max_oi_strike = max(strikes.keys(), key=lambda s: strikes[s]["call_oi"] + strikes[s]["put_oi"])
        
        # 计算 pain (价格偏离 max pain 的程度)
        deviation_pct = ((current_price - max_oi_strike) / max_oi_strike) * 100
        
        if abs(deviation_pct) < 3:
            signal = "接近 Max Pain"
        elif deviation_pct > 5:
            signal = "高于 Max Pain (可能回落)"
        elif deviation_pct < -5:
            signal = "低于 Max Pain (可能反弹)"
        else:
            signal = f"偏离 Max Pain {deviation_pct:+.1f}%"
        
        return {
            "max_pain": max_oi_strike,
            "current_price": round(current_price, 0),
            "deviation_pct": round(deviation_pct, 2),
            "signal": signal
        }
    
    def get_dvol(self) -> Dict[str, Any]:
        """获取 DVOL (Deribit 波动率指数)"""
        url = f"{self.base_url}/get_index_price"
        params = {"index_name": f"dvol_{self.currency.lower()}"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            dvol = data.get("result", {}).get("index_price", 0)
            
            # DVOL 信号
            if dvol > 80:
                signal = "极高波动率 (恐慌)"
            elif dvol > 60:
                signal = "高波动率"
            elif dvol > 40:
                signal = "正常波动率"
            else:
                signal = "低波动率 (平静)"
            
            return {
                "dvol": round(dvol, 2),
                "signal": signal
            }
        except:
            return {"dvol": 0, "signal": "数据获取失败"}
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 获取数据
        index_price = self.get_index_price()
        book_summary = self.get_book_summary()
        hv = self.get_historical_volatility()
        dvol = self.get_dvol()
        
        # 分析
        pcr = self.analyze_pcr(book_summary)
        max_pain = self.analyze_max_pain(book_summary, index_price)
        
        # 综合判断
        impacts = []
        if "impact" in pcr:
            impacts.append(pcr["impact"])
        
        bullish = impacts.count("bullish")
        bearish = impacts.count("bearish")
        
        if bullish > bearish:
            bias = "bullish"
            confidence = 5 + bullish
        elif bearish > bullish:
            bias = "bearish"
            confidence = 5 + bearish
        else:
            bias = "neutral"
            confidence = 5
        
        # 要点
        key_points = []
        if "pcr_oi" in pcr:
            key_points.append(f"PCR (OI): {pcr['pcr_oi']:.2f} - {pcr.get('signal', '')}")
        if "max_pain" in max_pain:
            key_points.append(f"Max Pain: ${max_pain['max_pain']:,} ({max_pain.get('signal', '')})")
        if "dvol" in dvol and dvol["dvol"] > 0:
            key_points.append(f"DVOL: {dvol['dvol']:.1f} - {dvol.get('signal', '')}")
        
        return {
            "agent": "options",
            "timestamp": timestamp,
            "index_price": index_price,
            "bias": bias,
            "confidence": confidence,
            "pcr": pcr,
            "max_pain": max_pain,
            "dvol": dvol,
            "historical_volatility": hv,
            "key_points": key_points,
            "alerts": []
        }


def main():
    analyst = OptionsAnalyst("BTC")
    result = analyst.analyze()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
