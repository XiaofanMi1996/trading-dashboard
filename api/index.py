#!/usr/bin/env python3
"""
Trading Dashboard API
FastAPI 后端，提供实时数据
Vercel 部署版本
"""

import sys
import os

# Vercel 部署时，所有文件都在同一目录
BASE_DIR = os.path.dirname(__file__)
sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# 导入分析模块（同目录）
from derivatives_analysis import DerivativesAnalyst
from technical_analysis import TechnicalAnalyst
from orderflow_analysis import OrderFlowAnalyst
from options_analysis import OptionsAnalyst
from macro_analysis import MacroAnalyst
from onchain_analysis import OnchainAnalyst
from coinbase_premium import get_coinbase_premium
from signal_scorer import SignalScorer
from smartmoney_analysis import SmartMoneyAnalyst

app = FastAPI(title="Trading Dashboard", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
static_path = os.path.join(os.path.dirname(__file__), "../static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")


def get_timestamp():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


@app.get("/")
async def index():
    """首页"""
    index_path = os.path.join(BASE_DIR, "templates/index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Trading Dashboard API", "docs": "/docs"}


@app.get("/api/price")
async def get_price():
    """获取当前价格"""
    try:
        import requests
        resp = requests.get("https://api.binance.com/api/v3/ticker/price", 
                          params={"symbol": "BTCUSDT"}, timeout=5)
        price = float(resp.json()["price"])
        
        # 24H 变化
        resp24 = requests.get("https://api.binance.com/api/v3/ticker/24hr",
                             params={"symbol": "BTCUSDT"}, timeout=5)
        data24 = resp24.json()
        
        return {
            "timestamp": get_timestamp(),
            "symbol": "BTCUSDT",
            "price": price,
            "change_24h": float(data24.get("priceChangePercent", 0)),
            "high_24h": float(data24.get("highPrice", 0)),
            "low_24h": float(data24.get("lowPrice", 0)),
            "volume_24h": float(data24.get("quoteVolume", 0))
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/six-dimensions")
async def get_six_dimensions():
    """六维分析"""
    try:
        technical = TechnicalAnalyst("BTCUSDT")
        tech_data = technical.analyze()
        
        derivatives = DerivativesAnalyst("BTCUSDT")
        deriv_data = derivatives.analyze()
        
        orderflow = OrderFlowAnalyst("BTCUSDT")
        flow_data = orderflow.analyze()
        
        cb_premium = get_coinbase_premium()
        
        return {
            "timestamp": get_timestamp(),
            "dimensions": {
                "ema": {
                    "name": "EMA多周期",
                    "timeframes": tech_data.get("ema_status", {}),
                    "bias": tech_data.get("bias", "neutral")
                },
                "bollinger": {
                    "name": "布林带",
                    "data": tech_data.get("bollinger", {}),
                    "position_pct": tech_data.get("bollinger", {}).get("position", 50)
                },
                "macd_rsi": {
                    "name": "MACD/RSI",
                    "macd": tech_data.get("macd", {}),
                    "rsi": tech_data.get("rsi", {})
                },
                "coinbase_premium": {
                    "name": "Coinbase溢价",
                    "premium_pct": cb_premium.get("premium_pct", 0),
                    "signal": cb_premium.get("signal", "neutral"),
                    "description": cb_premium.get("description", "")
                },
                "liquidation": {
                    "name": "清算数据",
                    "data": deriv_data.get("liquidation", {}),
                    "long_short_ratio": deriv_data.get("long_short_ratio", {}).get("top_accounts", {}).get("long_pct", 50),
                    "funding": deriv_data.get("funding", {}).get("current", 0),
                    "oi_change_24h": deriv_data.get("open_interest", {}).get("history", {}).get("change_24h_pct", 0)
                },
                "orderbook": {
                    "name": "订单流",
                    "cvd": flow_data.get("cvd", {}),
                    "bias": flow_data.get("bias", "neutral")
                }
            },
            "technical_raw": tech_data.get("raw", {})
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/agents")
async def get_agents():
    """6 Agent 分析"""
    try:
        results = {}
        
        analysts = {
            "derivatives": DerivativesAnalyst("BTCUSDT"),
            "technical": TechnicalAnalyst("BTCUSDT"),
            "orderflow": OrderFlowAnalyst("BTCUSDT"),
            "options": OptionsAnalyst("BTC"),
            "macro": MacroAnalyst(),
            "onchain": OnchainAnalyst()
        }
        
        for name, analyst in analysts.items():
            try:
                data = analyst.analyze()
                results[name] = {
                    "bias": data.get("bias", "neutral"),
                    "confidence": data.get("confidence", 5),
                    "key_points": data.get("key_points", [])[:3]
                }
            except Exception as e:
                results[name] = {"error": str(e), "bias": "neutral", "confidence": 0}
        
        # 综合评分
        scorer = SignalScorer()
        score = scorer.score_all({"analyses": results})
        
        return {
            "timestamp": get_timestamp(),
            "agents": results,
            "signal_score": score
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/framework")
async def get_framework():
    """周度框架"""
    try:
        framework_path = os.path.join(BASE_DIR, "weekly_framework.json")
        with open(framework_path, "r") as f:
            framework = json.load(f)
        
        return {
            "timestamp": get_timestamp(),
            "framework": framework
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/market-state")
async def get_market_state():
    """盘面状态"""
    return {
        "timestamp": get_timestamp(),
        "state": {}
    }


@app.get("/api/key-levels")
async def get_key_levels():
    """关键位"""
    try:
        framework_path = os.path.join(BASE_DIR, "weekly_framework.json")
        with open(framework_path, "r") as f:
            framework = json.load(f)
        
        # 获取当前价格
        import requests
        resp = requests.get("https://api.binance.com/api/v3/ticker/price",
                          params={"symbol": "BTCUSDT"}, timeout=5)
        price = float(resp.json()["price"])
        
        trade_zones = framework.get("trade_zones", {})
        
        # 判断当前区间和状态
        current_zone = None
        current_status = "观望中"
        
        for zone in trade_zones.get("resistance", []):
            if zone["range"][0] <= price <= zone["range"][1]:
                current_zone = {"type": "resistance", "zone": zone}
                current_status = f"在 {zone['name']} 压力区"
                break
            elif price < zone["range"][0] and price > zone["range"][0] * 0.98:
                current_status = f"接近 {zone['name']} ({((zone['range'][0] - price) / price * 100):.1f}%)"
        
        if not current_zone:
            for zone in trade_zones.get("support", []):
                if zone["range"][0] <= price <= zone["range"][1]:
                    current_zone = {"type": "support", "zone": zone}
                    current_status = f"在 {zone['name']} 支撑区"
                    break
                elif price > zone["range"][1] and price < zone["range"][1] * 1.02:
                    current_status = f"接近 {zone['name']} ({((price - zone['range'][1]) / price * 100):.1f}%)"
        
        return {
            "timestamp": get_timestamp(),
            "price": price,
            "current_zone": current_zone,
            "current_status": current_status,
            "resistance_zones": trade_zones.get("resistance", []),
            "support_zones": trade_zones.get("support", []),
            "key_ema": framework.get("key_ema", {})
        }
    except Exception as e:
        return {"error": str(e)}


def get_daily_comparison():
    """获取较昨日对比数据 - Vercel 版本使用 SmartMoney 内存数据"""
    try:
        # Vercel 无法持久化存储，从 SmartMoney 历史获取
        sm_analyst = SmartMoneyAnalyst("BTCUSDT")
        sm_data = sm_analyst.analyze()
        
        history = sm_data.get("history", [])
        current = sm_data.get("current", {})
        
        if not current or len(history) < 2:
            return None
        
        # 今天数据 = 当前
        today_data = {
            "time": current.get("snapshot_time", "").split(" ")[1][:5] if " " in current.get("snapshot_time", "") else "now",
            "price": current.get("price", 0),
            "sm_long_usdt": current.get("long_position_usdt", 0),
            "sm_short_usdt": current.get("short_position_usdt", 0),
            "sm_long_short_ratio": current.get("long_short_ratio_pct", 50),
            "oi": 0,
            "funding_rate": 0
        }
        
        # 昨天数据 = 历史最后一条（约24小时前）
        oldest = history[-1] if history else current
        yesterday_data = {
            "time": oldest.get("snapshot_time", "").split(" ")[1][:5] if " " in oldest.get("snapshot_time", "") else "24h ago",
            "price": oldest.get("price", 0),
            "sm_long_usdt": oldest.get("long_position_usdt", 0),
            "sm_short_usdt": oldest.get("short_position_usdt", 0),
            "sm_long_short_ratio": oldest.get("long_short_ratio_pct", 50),
            "oi": 0,
            "funding_rate": 0
        }
        
        return {
            "today": today_data,
            "yesterday": yesterday_data,
            "compare_time": "vs 历史记录"
        }
    except:
        return None


@app.get("/api/all")
async def get_all():
    """获取所有数据（一次请求）"""
    price_data = await get_price()
    six_dim = await get_six_dimensions()
    agents = await get_agents()
    framework = await get_framework()
    key_levels = await get_key_levels()
    market_state = await get_market_state()
    
    # Smart Money 数据
    try:
        sm_analyst = SmartMoneyAnalyst("BTCUSDT")
        smartmoney = sm_analyst.analyze()
    except:
        smartmoney = {}
    
    # Daily Comparison
    daily_comparison = get_daily_comparison()
    
    return {
        "timestamp": get_timestamp(),
        "price": price_data,
        "six_dimensions": six_dim.get("dimensions", {}),
        "technical_raw": six_dim.get("technical_raw", {}),
        "agents": agents.get("agents", {}),
        "signal_score": agents.get("signal_score", {}),
        "framework": framework.get("framework", {}),
        "key_levels": key_levels,
        "market_state": market_state.get("state", {}),
        "smartmoney": smartmoney,
        "daily_comparison": daily_comparison
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
