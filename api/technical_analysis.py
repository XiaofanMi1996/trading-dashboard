#!/usr/bin/env python3
"""
Technical Analyst - 技术分析脚本
数据源: Binance API
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Tuple
import statistics

class TechnicalAnalyst:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.base_url = "https://fapi.binance.com"
        self.ema_periods = [20, 50, 200, 300, 400]
        
    def get_klines(self, interval: str, limit: int = 500) -> List[Dict]:
        """获取K线数据"""
        url = f"{self.base_url}/fapi/v1/klines"
        params = {"symbol": self.symbol, "interval": interval, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return [{
                "time": x[0],
                "open": float(x[1]),
                "high": float(x[2]),
                "low": float(x[3]),
                "close": float(x[4]),
                "volume": float(x[5])
            } for x in data]
        except Exception as e:
            return []
    
    def calc_ema(self, prices: List[float], period: int) -> List[float]:
        """计算EMA"""
        if len(prices) < period:
            return []
        
        multiplier = 2 / (period + 1)
        ema = [sum(prices[:period]) / period]  # SMA as first EMA
        
        for price in prices[period:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        
        return ema
    
    def calc_rsi(self, prices: List[float], period: int = 14) -> float:
        """计算RSI"""
        if len(prices) < period + 1:
            return 50
        
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [c if c > 0 else 0 for c in changes[-period:]]
        losses = [-c if c < 0 else 0 for c in changes[-period:]]
        
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)
    
    def calc_macd(self, prices: List[float]) -> Dict[str, float]:
        """计算MACD"""
        if len(prices) < 26:
            return {"macd": 0, "signal": 0, "histogram": 0}
        
        ema12 = self.calc_ema(prices, 12)
        ema26 = self.calc_ema(prices, 26)
        
        # Align lengths
        min_len = min(len(ema12), len(ema26))
        ema12 = ema12[-min_len:]
        ema26 = ema26[-min_len:]
        
        macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
        signal_line = self.calc_ema(macd_line, 9) if len(macd_line) >= 9 else [0]
        
        macd = macd_line[-1] if macd_line else 0
        signal = signal_line[-1] if signal_line else 0
        histogram = macd - signal
        
        return {
            "macd": round(macd, 2),
            "signal": round(signal, 2),
            "histogram": round(histogram, 2)
        }
    
    def calc_bollinger(self, prices: List[float], period: int = 20, std_dev: int = 2) -> Dict[str, float]:
        """计算布林带"""
        if len(prices) < period:
            return {"upper": 0, "middle": 0, "lower": 0, "position": 50}
        
        recent = prices[-period:]
        middle = sum(recent) / period
        std = statistics.stdev(recent)
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        current = prices[-1]
        position = ((current - lower) / (upper - lower)) * 100 if upper != lower else 50
        
        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "position": round(position, 1)
        }
    
    def analyze_timeframe(self, interval: str) -> Dict[str, Any]:
        """分析单个时间周期"""
        klines = self.get_klines(interval, 500)
        if not klines:
            return {"error": "No data"}
        
        closes = [k["close"] for k in klines]
        volumes = [k["volume"] for k in klines]
        current_price = closes[-1]
        
        # EMA
        emas = {}
        for period in self.ema_periods:
            ema_values = self.calc_ema(closes, period)
            if ema_values:
                emas[f"ema{period}"] = round(ema_values[-1], 2)
        
        # EMA 状态判断
        if len(emas) >= 3:
            ema20 = emas.get("ema20", current_price)
            ema50 = emas.get("ema50", current_price)
            ema200 = emas.get("ema200", current_price)
            
            if current_price > ema20 > ema50 > ema200:
                ema_status = "多头排列"
                ema_bias = "bullish"
            elif current_price < ema20 < ema50 < ema200:
                ema_status = "空头排列"
                ema_bias = "bearish"
            elif current_price > ema20 and current_price > ema50:
                ema_status = "偏多"
                ema_bias = "bullish"
            elif current_price < ema20 and current_price < ema50:
                ema_status = "偏空"
                ema_bias = "bearish"
            else:
                ema_status = "震荡"
                ema_bias = "neutral"
        else:
            ema_status = "数据不足"
            ema_bias = "neutral"
        
        # RSI
        rsi = self.calc_rsi(closes)
        
        # MACD
        macd_data = self.calc_macd(closes)
        macd_signal = "金叉" if macd_data["histogram"] > 0 else "死叉"
        
        # 布林带
        boll = self.calc_bollinger(closes)
        
        # 量价关系
        if len(volumes) >= 5:
            recent_vol = sum(volumes[-5:]) / 5
            prev_vol = sum(volumes[-10:-5]) / 5 if len(volumes) >= 10 else recent_vol
            vol_change = ((recent_vol - prev_vol) / prev_vol) * 100 if prev_vol else 0
            
            price_change = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if len(closes) >= 5 else 0
            
            if price_change > 0 and vol_change > 10:
                vol_signal = "放量上涨"
            elif price_change > 0 and vol_change < -10:
                vol_signal = "缩量上涨"
            elif price_change < 0 and vol_change > 10:
                vol_signal = "放量下跌"
            elif price_change < 0 and vol_change < -10:
                vol_signal = "缩量下跌"
            else:
                vol_signal = "量价平稳"
        else:
            vol_signal = "数据不足"
            vol_change = 0
        
        return {
            "price": current_price,
            "emas": emas,
            "ema_status": ema_status,
            "ema_bias": ema_bias,
            "rsi": rsi,
            "macd": macd_data,
            "macd_signal": macd_signal,
            "bollinger": boll,
            "volume": {
                "change_pct": round(vol_change, 1),
                "signal": vol_signal
            }
        }
    
    def find_key_levels(self, analyses: Dict[str, Dict]) -> Dict[str, List[float]]:
        """识别关键支撑压力位"""
        all_emas = []
        current_price = 0
        
        for tf, data in analyses.items():
            if "emas" in data:
                current_price = data["price"]
                for name, value in data["emas"].items():
                    all_emas.append(value)
        
        if not current_price:
            return {"resistance": [], "support": []}
        
        # 分类
        resistance = sorted(set(e for e in all_emas if e > current_price))[:3]
        support = sorted(set(e for e in all_emas if e < current_price), reverse=True)[:3]
        
        return {
            "resistance": [round(r, 0) for r in resistance],
            "support": [round(s, 0) for s in support]
        }
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 分析各周期
        timeframes = {
            "15m": "15m",
            "1h": "1h",
            "4h": "4h",
            "1d": "1d",
            "1w": "1w"
        }
        
        analyses = {}
        for name, interval in timeframes.items():
            analyses[name] = self.analyze_timeframe(interval)
        
        # 提取趋势
        trend = {}
        ema_status = {}
        macd = {}
        rsi = {}
        
        for tf, data in analyses.items():
            if "ema_bias" in data:
                trend[tf] = data["ema_bias"]
                ema_status[tf] = data["ema_status"]
                macd[tf] = data.get("macd_signal", "")
                rsi[tf] = data.get("rsi", 50)
        
        # 关键位
        key_levels = self.find_key_levels(analyses)
        
        # 综合判断 (更敏感 - 只要多数周期一致就给方向)
        bullish_count = sum(1 for v in trend.values() if v == "bullish")
        bearish_count = sum(1 for v in trend.values() if v == "bearish")
        
        # 优先看中大周期 (4h, 1d)
        big_tf_bullish = sum(1 for tf in ["4h", "1d"] if trend.get(tf) == "bullish")
        big_tf_bearish = sum(1 for tf in ["4h", "1d"] if trend.get(tf) == "bearish")
        
        if big_tf_bullish >= 1 and bullish_count > bearish_count:
            bias = "bullish"
            confidence = 5 + bullish_count + big_tf_bullish
        elif big_tf_bearish >= 1 and bearish_count > bullish_count:
            bias = "bearish"
            confidence = 5 + bearish_count + big_tf_bearish
        elif bullish_count > bearish_count:
            bias = "bullish"
            confidence = 4 + bullish_count
        elif bearish_count > bullish_count:
            bias = "bearish"
            confidence = 4 + bearish_count
        else:
            bias = "neutral"
            confidence = 5
        
        # 要点
        key_points = []
        for tf in ["4h", "1h", "1d"]:
            if tf in ema_status:
                key_points.append(f"{tf.upper()} {ema_status[tf]}")
        
        if "1d" in analyses and "bollinger" in analyses["1d"]:
            boll_pos = analyses["1d"]["bollinger"]["position"]
            if boll_pos > 80:
                key_points.append("日线布林带上轨附近")
            elif boll_pos < 20:
                key_points.append("日线布林带下轨附近")
        
        if "4h" in analyses and "volume" in analyses["4h"]:
            key_points.append(f"4H {analyses['4h']['volume']['signal']}")
        
        return {
            "agent": "technical",
            "timestamp": timestamp,
            "symbol": self.symbol,
            "price": analyses.get("1h", {}).get("price", 0),
            "bias": bias,
            "confidence": min(confidence, 10),
            "trend": trend,
            "ema_status": ema_status,
            "macd": macd,
            "rsi": rsi,
            "key_levels": key_levels,
            "bollinger": analyses.get("1d", {}).get("bollinger", {}),
            "key_points": key_points,
            "alerts": [],
            "raw": {tf: {k: v for k, v in data.items() if k != "emas"} for tf, data in analyses.items()}
        }


def main():
    analyst = TechnicalAnalyst("BTCUSDT")
    result = analyst.analyze()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
