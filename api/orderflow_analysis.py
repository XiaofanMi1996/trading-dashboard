#!/usr/bin/env python3
"""
OrderFlow Analyst - 订单流分析脚本
数据源: Binance Futures API + Coinglass (爬取)

注意: Binance API 深度有限 (500档约±0.5%)
远处大墙需看 Coinglass: https://www.coinglass.com/zh/large-orderbook-statistics
"""

import requests
import json
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List
from collections import defaultdict

# Coinglass 爬虫
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

def parse_value(s):
    """解析金额字符串，如 $246.50M -> 246500000"""
    if not s:
        return 0
    s = s.replace('$', '').replace(',', '').strip()
    multiplier = 1
    if s.endswith('B'):
        multiplier = 1_000_000_000
        s = s[:-1]
    elif s.endswith('M'):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith('K'):
        multiplier = 1_000
        s = s[:-1]
    try:
        return float(s) * multiplier
    except:
        return 0


def scrape_coinglass_liquidation():
    """爬取 Coinglass 清算数据"""
    if not SELENIUM_AVAILABLE:
        return {"error": "selenium not available", "success": False}
    
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
    
    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get('https://www.coinglass.com/liquidations')
        time.sleep(5)
        
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        result = {"success": True}
        
        # 24H 爆仓
        match_24h = re.search(r'24h Rekt\s*\$?([\d.]+[KMB]?)\s*Long\s*\$?([\d.]+[KMB]?)\s*Short\s*\$?([\d.]+[KMB]?)', page_text)
        if match_24h:
            result["liquidation_24h"] = {
                "total": parse_value(match_24h.group(1)),
                "long": parse_value(match_24h.group(2)),
                "short": parse_value(match_24h.group(3))
            }
        
        # 1H 爆仓
        match_1h = re.search(r'1h Rekt\s*\$?([\d.]+[KMB]?)\s*Long\s*\$?([\d.]+[KMB]?)\s*Short\s*\$?([\d.]+[KMB]?)', page_text)
        if match_1h:
            result["liquidation_1h"] = {
                "total": parse_value(match_1h.group(1)),
                "long": parse_value(match_1h.group(2)),
                "short": parse_value(match_1h.group(3))
            }
        
        # 4H 爆仓
        match_4h = re.search(r'4h Rekt\s*\$?([\d.]+[KMB]?)\s*Long\s*\$?([\d.]+[KMB]?)\s*Short\s*\$?([\d.]+[KMB]?)', page_text)
        if match_4h:
            result["liquidation_4h"] = {
                "total": parse_value(match_4h.group(1)),
                "long": parse_value(match_4h.group(2)),
                "short": parse_value(match_4h.group(3))
            }
        
        # 计算信号
        if "liquidation_24h" in result:
            liq = result["liquidation_24h"]
            total = liq["total"]
            long_pct = liq["long"] / total * 100 if total > 0 else 50
            short_pct = liq["short"] / total * 100 if total > 0 else 50
            
            if total > 1_000_000_000:
                result["signal_level"] = "extreme"
            elif total > 500_000_000:
                result["signal_level"] = "high"
            elif total > 200_000_000:
                result["signal_level"] = "medium"
            else:
                result["signal_level"] = "normal"
            
            if short_pct > 70:
                result["liq_bias"] = "bullish"
                result["liq_note"] = f"空头被清洗 ({short_pct:.0f}%)"
            elif long_pct > 70:
                result["liq_bias"] = "bearish"
                result["liq_note"] = f"多头被清洗 ({long_pct:.0f}%)"
            else:
                result["liq_bias"] = "neutral"
                result["liq_note"] = f"多空均衡 ({long_pct:.0f}%/{short_pct:.0f}%)"
        
        return result
        
    except Exception as e:
        return {"error": str(e), "success": False}
    finally:
        if driver:
            driver.quit()


class OrderFlowAnalyst:
    def __init__(self, symbol: str = "BTCUSDT", use_coinglass: bool = True):
        self.symbol = symbol
        self.base_url = "https://fapi.binance.com"
        self.large_order_threshold = 1.0  # BTC, 约 $70K
        self.whale_order_threshold = 5.0  # BTC, 约 $350K
        self.use_coinglass = use_coinglass
        
    def get_agg_trades(self, limit: int = 1000) -> List[Dict]:
        """获取聚合成交记录"""
        url = f"{self.base_url}/fapi/v1/aggTrades"
        params = {"symbol": self.symbol, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return [{
                "price": float(t["p"]),
                "qty": float(t["q"]),
                "time": t["T"],
                "is_buyer_maker": t["m"]  # True = 卖方主动 (taker sell)
            } for t in data]
        except Exception as e:
            return []
    
    def get_klines(self, interval: str = "1h", limit: int = 4) -> List[Dict]:
        """获取K线数据（用于计算多周期CVD）"""
        url = f"{self.base_url}/fapi/v1/klines"
        params = {"symbol": self.symbol, "interval": interval, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return [{
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "taker_buy_volume": float(k[9]),  # Taker buy base asset volume
                "taker_sell_volume": float(k[5]) - float(k[9])  # 总量 - 买量 = 卖量
            } for k in data]
        except Exception as e:
            return []
    
    def get_orderbook(self, limit: int = 50) -> Dict[str, Any]:
        """获取订单簿"""
        url = f"{self.base_url}/fapi/v1/depth"
        params = {"symbol": self.symbol, "limit": limit}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            
            bids = [[float(p), float(q)] for p, q in data["bids"]]
            asks = [[float(p), float(q)] for p, q in data["asks"]]
            
            return {"bids": bids, "asks": asks}
        except Exception as e:
            return {"bids": [], "asks": []}
    
    def get_ticker(self) -> Dict[str, Any]:
        """获取24H统计"""
        url = f"{self.base_url}/fapi/v1/ticker/24hr"
        params = {"symbol": self.symbol}
        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            return {
                "price": float(data["lastPrice"]),
                "volume_24h": float(data["volume"]),
                "quote_volume_24h": float(data["quoteVolume"]),
                "price_change_pct": float(data["priceChangePercent"])
            }
        except Exception as e:
            return {}
    
    def analyze_cvd(self, trades: List[Dict]) -> Dict[str, Any]:
        """计算 CVD (Cumulative Volume Delta) - 短期快照"""
        if not trades:
            return {"error": "No trades data"}
        
        # 计算总 CVD
        buy_volume = 0
        sell_volume = 0
        
        for t in trades:
            if t["is_buyer_maker"]:
                sell_volume += t["qty"]
            else:
                buy_volume += t["qty"]
        
        cvd = buy_volume - sell_volume
        total_volume = buy_volume + sell_volume
        buy_ratio = buy_volume / total_volume if total_volume else 0.5
        
        return {
            "cvd_btc": round(cvd, 2),
            "buy_volume_btc": round(buy_volume, 2),
            "sell_volume_btc": round(sell_volume, 2),
            "buy_ratio": round(buy_ratio * 100, 1)
        }
    
    def analyze_cvd_multi_timeframe(self) -> Dict[str, Any]:
        """多周期 CVD 分析 - 使用 K 线 taker_buy_volume"""
        
        # 获取多周期数据
        klines_1h = self.get_klines("1h", 4)   # 最近 4 小时
        klines_4h = self.get_klines("4h", 4)   # 最近 16 小时
        
        results = {}
        
        # 1H CVD (最近 4 根 1H K线)
        if klines_1h:
            total_buy_1h = sum(k["taker_buy_volume"] for k in klines_1h)
            total_sell_1h = sum(k["taker_sell_volume"] for k in klines_1h)
            total_vol_1h = total_buy_1h + total_sell_1h
            buy_ratio_1h = total_buy_1h / total_vol_1h if total_vol_1h else 0.5
            cvd_1h = total_buy_1h - total_sell_1h
            
            # 趋势：对比前后两段
            if len(klines_1h) >= 2:
                first_half = klines_1h[:len(klines_1h)//2]
                second_half = klines_1h[len(klines_1h)//2:]
                first_cvd = sum(k["taker_buy_volume"] - k["taker_sell_volume"] for k in first_half)
                second_cvd = sum(k["taker_buy_volume"] - k["taker_sell_volume"] for k in second_half)
                
                if second_cvd > first_cvd * 1.3:
                    trend_1h = "买压增强"
                elif second_cvd < first_cvd * 0.7:
                    trend_1h = "卖压增强"
                else:
                    trend_1h = "持平"
            else:
                trend_1h = "数据不足"
            
            results["1h"] = {
                "cvd_btc": round(cvd_1h, 2),
                "buy_ratio": round(buy_ratio_1h * 100, 1),
                "trend": trend_1h
            }
        
        # 4H CVD (最近 4 根 4H K线 = 16小时)
        if klines_4h:
            total_buy_4h = sum(k["taker_buy_volume"] for k in klines_4h)
            total_sell_4h = sum(k["taker_sell_volume"] for k in klines_4h)
            total_vol_4h = total_buy_4h + total_sell_4h
            buy_ratio_4h = total_buy_4h / total_vol_4h if total_vol_4h else 0.5
            cvd_4h = total_buy_4h - total_sell_4h
            
            if len(klines_4h) >= 2:
                first_half = klines_4h[:len(klines_4h)//2]
                second_half = klines_4h[len(klines_4h)//2:]
                first_cvd = sum(k["taker_buy_volume"] - k["taker_sell_volume"] for k in first_half)
                second_cvd = sum(k["taker_buy_volume"] - k["taker_sell_volume"] for k in second_half)
                
                if second_cvd > first_cvd * 1.3:
                    trend_4h = "买压增强"
                elif second_cvd < first_cvd * 0.7:
                    trend_4h = "卖压增强"
                else:
                    trend_4h = "持平"
            else:
                trend_4h = "数据不足"
            
            results["4h"] = {
                "cvd_btc": round(cvd_4h, 2),
                "buy_ratio": round(buy_ratio_4h * 100, 1),
                "trend": trend_4h
            }
        
        # 综合信号：以 1H 为主，4H 为参考
        buy_ratio_avg = 50
        if "1h" in results and "4h" in results:
            # 加权平均：1H 权重 0.6，4H 权重 0.4
            buy_ratio_avg = results["1h"]["buy_ratio"] * 0.6 + results["4h"]["buy_ratio"] * 0.4
        elif "1h" in results:
            buy_ratio_avg = results["1h"]["buy_ratio"]
        
        if buy_ratio_avg > 55:
            signal = "买方主导"
            impact = "bullish"
        elif buy_ratio_avg < 45:
            signal = "卖方主导"
            impact = "bearish"
        else:
            signal = "多空均衡"
            impact = "neutral"
        
        # 综合趋势
        trends = []
        if "1h" in results:
            trends.append(results["1h"]["trend"])
        if "4h" in results:
            trends.append(results["4h"]["trend"])
        
        if "买压增强" in trends and "卖压增强" not in trends:
            overall_trend = "买压增强"
        elif "卖压增强" in trends and "买压增强" not in trends:
            overall_trend = "卖压增强"
        else:
            overall_trend = "持平"
        
        return {
            "timeframes": results,
            "buy_ratio_weighted": round(buy_ratio_avg, 1),
            "trend": overall_trend,
            "signal": signal,
            "impact": impact
        }
    
    def analyze_large_orders(self, trades: List[Dict]) -> Dict[str, Any]:
        """分析大单"""
        if not trades:
            return {"error": "No trades data"}
        
        large_buys = []
        large_sells = []
        whale_buys = []
        whale_sells = []
        
        for t in trades:
            qty = t["qty"]
            price = t["price"]
            
            if qty >= self.whale_order_threshold:
                if t["is_buyer_maker"]:
                    whale_sells.append({"qty": qty, "price": price})
                else:
                    whale_buys.append({"qty": qty, "price": price})
            elif qty >= self.large_order_threshold:
                if t["is_buyer_maker"]:
                    large_sells.append({"qty": qty, "price": price})
                else:
                    large_buys.append({"qty": qty, "price": price})
        
        total_large_buy = sum(o["qty"] for o in large_buys)
        total_large_sell = sum(o["qty"] for o in large_sells)
        total_whale_buy = sum(o["qty"] for o in whale_buys)
        total_whale_sell = sum(o["qty"] for o in whale_sells)
        
        # 信号判断
        large_ratio = total_large_buy / (total_large_buy + total_large_sell) if (total_large_buy + total_large_sell) else 0.5
        
        if len(whale_buys) > len(whale_sells) + 2:
            signal = "巨鲸买入"
            impact = "bullish"
        elif len(whale_sells) > len(whale_buys) + 2:
            signal = "巨鲸卖出"
            impact = "bearish"
        elif large_ratio > 0.6:
            signal = "大单偏多"
            impact = "bullish"
        elif large_ratio < 0.4:
            signal = "大单偏空"
            impact = "bearish"
        else:
            signal = "大单均衡"
            impact = "neutral"
        
        return {
            "large_buy_count": len(large_buys),
            "large_sell_count": len(large_sells),
            "large_buy_btc": round(total_large_buy, 2),
            "large_sell_btc": round(total_large_sell, 2),
            "whale_buy_count": len(whale_buys),
            "whale_sell_count": len(whale_sells),
            "whale_buy_btc": round(total_whale_buy, 2),
            "whale_sell_btc": round(total_whale_sell, 2),
            "signal": signal,
            "impact": impact
        }
    
    def analyze_orderbook(self, orderbook: Dict) -> Dict[str, Any]:
        """分析订单簿 (Binance 500档，约±0.5%范围)"""
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        
        if not bids or not asks:
            return {"error": "No orderbook data"}
        
        # 总量
        bid_total = sum(q for p, q in bids)
        ask_total = sum(q for p, q in asks)
        ratio = bid_total / ask_total if ask_total else 1
        
        # 找大墙 (按美元价值 >$500K)
        wall_threshold_usd = 500000
        current_price = bids[0][0] if bids else 70000
        
        bid_walls = []
        ask_walls = []
        
        for p, q in bids:
            value = p * q
            if value >= wall_threshold_usd:
                bid_walls.append({
                    "price": round(p, 0),
                    "qty_btc": round(q, 1),
                    "value_usd": round(value, 0)
                })
        
        for p, q in asks:
            value = p * q
            if value >= wall_threshold_usd:
                ask_walls.append({
                    "price": round(p, 0),
                    "qty_btc": round(q, 1),
                    "value_usd": round(value, 0)
                })
        
        # 墙的总价值
        bid_wall_total = sum(w["value_usd"] for w in bid_walls)
        ask_wall_total = sum(w["value_usd"] for w in ask_walls)
        wall_ratio = bid_wall_total / ask_wall_total if ask_wall_total else 1
        
        # 信号判断
        if wall_ratio > 1.5:
            signal = "买墙厚实 (支撑强)"
            impact = "bullish"
        elif wall_ratio < 0.67:
            signal = "卖墙厚实 (压力大)"
            impact = "bearish"
        else:
            signal = "挂单均衡"
            impact = "neutral"
        
        return {
            "bid_total_btc": round(bid_total, 1),
            "ask_total_btc": round(ask_total, 1),
            "ratio": round(ratio, 2),
            "bid_walls": bid_walls[:5],
            "ask_walls": ask_walls[:5],
            "bid_wall_total_usd": bid_wall_total,
            "ask_wall_total_usd": ask_wall_total,
            "wall_ratio": round(wall_ratio, 2),
            "signal": signal,
            "impact": impact,
            "note": "仅显示±0.5%范围，远处大墙看Coinglass"
        }
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 获取数据
        trades = self.get_agg_trades(1000)
        orderbook = self.get_orderbook(50)
        ticker = self.get_ticker()
        
        # 分析 - 使用多周期 CVD 代替短期快照
        cvd_snapshot = self.analyze_cvd(trades)  # 保留快照数据
        cvd_multi = self.analyze_cvd_multi_timeframe()  # 新增多周期分析
        large_orders = self.analyze_large_orders(trades)
        ob_analysis = self.analyze_orderbook(orderbook)
        
        # Coinglass 清算数据
        coinglass_data = None
        if self.use_coinglass and SELENIUM_AVAILABLE:
            coinglass_data = scrape_coinglass_liquidation()
        
        # 综合判断 - 以多周期 CVD 为主
        impacts = []
        if "impact" in cvd_multi:
            impacts.append(cvd_multi["impact"])
            impacts.append(cvd_multi["impact"])  # CVD 权重 x2
        if "impact" in large_orders:
            impacts.append(large_orders["impact"])
        if "impact" in ob_analysis:
            impacts.append(ob_analysis["impact"])
        
        # 加入清算数据的 bias
        if coinglass_data and coinglass_data.get("success"):
            liq_bias = coinglass_data.get("liq_bias")
            if liq_bias == "bullish":
                impacts.append("bullish")
                impacts.append("bullish")  # 清算数据权重 x2
            elif liq_bias == "bearish":
                impacts.append("bearish")
                impacts.append("bearish")
        
        bullish = impacts.count("bullish")
        bearish = impacts.count("bearish")
        
        # 更敏感的判断
        if bullish > bearish:
            bias = "bullish"
            confidence = 5 + bullish
        elif bearish > bullish:
            bias = "bearish"
            confidence = 5 + bearish
        else:
            bias = "neutral"
            confidence = 5
        
        # 要点 - 展示多周期数据
        key_points = []
        tf_1h = cvd_multi.get("timeframes", {}).get("1h", {})
        tf_4h = cvd_multi.get("timeframes", {}).get("4h", {})
        
        key_points.append(f"CVD 1H: {tf_1h.get('buy_ratio', 50)}% 买方 ({tf_1h.get('trend', 'N/A')})")
        key_points.append(f"CVD 4H: {tf_4h.get('buy_ratio', 50)}% 买方 ({tf_4h.get('trend', 'N/A')})")
        key_points.append(f"综合: {cvd_multi.get('signal', 'N/A')}")
        
        if "signal" in large_orders:
            key_points.append(f"大单: {large_orders['signal']}")
        if "signal" in ob_analysis:
            key_points.append(f"盘口: {ob_analysis['signal']}")
        
        # 加入清算数据要点
        if coinglass_data and coinglass_data.get("success"):
            liq_24h = coinglass_data.get("liquidation_24h", {})
            if liq_24h:
                total_m = liq_24h.get("total", 0) / 1e6
                key_points.append(f"24H爆仓: ${total_m:.1f}M ({coinglass_data.get('liq_note', '')})")
        
        alerts = []
        # 清算异动警报
        if coinglass_data and coinglass_data.get("success"):
            liq_24h = coinglass_data.get("liquidation_24h", {})
            total = liq_24h.get("total", 0)
            if total > 1_000_000_000:
                alerts.append(f"🚨 24H 爆仓超 $1B ({total/1e9:.2f}B)，极端行情")
            elif total > 500_000_000:
                alerts.append(f"⚠️ 24H 爆仓 ${total/1e6:.0f}M，高波动")
        
        result = {
            "agent": "orderflow",
            "timestamp": timestamp,
            "symbol": self.symbol,
            "price": ticker.get("price", 0),
            "bias": bias,
            "confidence": min(confidence, 10),
            "cvd_snapshot": cvd_snapshot,  # 短期快照
            "cvd": cvd_multi,  # 多周期分析 (主要)
            "large_orders": large_orders,
            "orderbook": ob_analysis,
            "key_points": key_points,
            "alerts": alerts
        }
        
        # 加入 Coinglass 数据
        if coinglass_data and coinglass_data.get("success"):
            result["coinglass"] = {
                "liquidation_24h": coinglass_data.get("liquidation_24h"),
                "liquidation_1h": coinglass_data.get("liquidation_1h"),
                "liquidation_4h": coinglass_data.get("liquidation_4h"),
                "signal_level": coinglass_data.get("signal_level"),
                "liq_bias": coinglass_data.get("liq_bias"),
                "liq_note": coinglass_data.get("liq_note")
            }
        
        return result


def main():
    analyst = OrderFlowAnalyst("BTCUSDT")
    result = analyst.analyze()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
