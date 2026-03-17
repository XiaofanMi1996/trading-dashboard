#!/usr/bin/env python3
"""
Smart Money Analysis - Vercel 版本（无数据库，只读实时数据）
"""

import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import requests

class SmartMoneyAnalyst:
    def __init__(self, symbol: str = "BTCUSDT"):
        self.symbol = symbol
        self.base_url = "https://www.binance.com/bapi/futures/v1/public/future/smart-money/signal"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Referer": f"https://www.binance.com/zh-CN/smart-money/signal/{symbol}"
        }
    
    def _get_price(self) -> float:
        try:
            resp = requests.get(
                "https://fapi.binance.com/fapi/v1/ticker/price",
                params={"symbol": self.symbol},
                timeout=5
            )
            return float(resp.json().get('price', 0))
        except:
            return 0
    
    def fetch_overview(self) -> Optional[Dict]:
        try:
            resp = requests.get(
                f"{self.base_url}/overview",
                params={"symbol": self.symbol},
                headers=self.headers,
                timeout=10
            )
            data = resp.json()
            if data.get("success") and data.get("data"):
                return data["data"]
            return None
        except Exception as e:
            print(f"Fetch overview error: {e}")
            return None
    
    def analyze(self) -> Dict[str, Any]:
        sgt = timezone(timedelta(hours=8))
        timestamp = datetime.now(sgt).isoformat()
        
        overview = self.fetch_overview()
        if not overview:
            return {
                "agent": "smartmoney",
                "timestamp": timestamp,
                "symbol": self.symbol,
                "bias": "neutral",
                "confidence": 1,
                "current": None,
                "changes": {},
                "history": [],
                "key_points": ["⚠️ 聪明钱数据获取失败"]
            }
        
        price = self._get_price()
        if price == 0:
            price = 1
        
        now = datetime.now(sgt)
        snapshot_time = now.strftime("%Y-%m-%d %H:%M:%S")
        
        long_traders = overview.get('longTraders', 0)
        long_qty = overview.get('longTradersQty', 0)
        long_avg_price = overview.get('longTradersAvgEntryPrice', 0)
        long_profit_traders = overview.get('longProfitTraders', 0)
        
        short_traders = overview.get('shortTraders', 0)
        short_qty = overview.get('shortTradersQty', 0)
        short_avg_price = overview.get('shortTradersAvgEntryPrice', 0)
        short_profit_traders = overview.get('shortProfitTraders', 0)
        
        long_position_usdt = long_qty * price
        short_position_usdt = short_qty * price
        
        long_unrealized_pnl = (price - long_avg_price) * long_qty if long_avg_price > 0 else 0
        short_unrealized_pnl = (short_avg_price - price) * short_qty if short_avg_price > 0 else 0
        
        long_profitable_pct = (long_profit_traders / long_traders * 100) if long_traders > 0 else 0
        short_profitable_pct = (short_profit_traders / short_traders * 100) if short_traders > 0 else 0
        
        long_short_ratio_pct = (long_position_usdt / short_position_usdt * 100) if short_position_usdt > 0 else 0
        
        current = {
            'snapshot_time': snapshot_time,
            'price': price,
            'long_traders': long_traders,
            'long_position_usdt': long_position_usdt,
            'long_avg_entry_price': long_avg_price,
            'long_unrealized_pnl': long_unrealized_pnl,
            'long_profitable_pct': long_profitable_pct,
            'short_traders': short_traders,
            'short_position_usdt': short_position_usdt,
            'short_avg_entry_price': short_avg_price,
            'short_unrealized_pnl': short_unrealized_pnl,
            'short_profitable_pct': short_profitable_pct,
            'long_short_ratio_pct': long_short_ratio_pct
        }
        
        bias = "neutral"
        confidence = 5
        key_points = []
        
        if long_short_ratio_pct > 200:
            bias = "bullish"
            confidence += 1
            key_points.append(f"多空比 {long_short_ratio_pct:.0f}%，多头占优")
        elif long_short_ratio_pct < 80:
            bias = "bearish"
            confidence += 1
            key_points.append(f"多空比 {long_short_ratio_pct:.0f}%，空头占优")
        
        return {
            "agent": "smartmoney",
            "timestamp": timestamp,
            "symbol": self.symbol,
            "bias": bias,
            "confidence": min(10, confidence),
            "current": current,
            "changes": {},
            "history": [],  # Vercel 版本无历史
            "key_points": key_points
        }
