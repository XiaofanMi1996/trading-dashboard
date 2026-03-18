#!/usr/bin/env python3
"""
Trading Dashboard API
FastAPI 后端，提供实时数据
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../scripts"))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

# 缓存
_cache = {}
_cache_ttl = 30  # 30秒缓存

def get_cached(key: str, fetch_func, ttl: int = None):
    """带缓存的数据获取"""
    if ttl is None:
        ttl = _cache_ttl
    now = time.time()
    if key in _cache:
        data, ts = _cache[key]
        if now - ts < ttl:
            return data
    try:
        data = fetch_func()
        _cache[key] = (data, now)
        return data
    except Exception as e:
        # 如果有旧缓存，返回旧数据
        if key in _cache:
            return _cache[key][0]
        raise e

# 导入分析模块
from derivatives_analysis import DerivativesAnalyst
from technical_analysis import TechnicalAnalyst
from orderflow_analysis import OrderFlowAnalyst
from options_analysis import OptionsAnalyst
from macro_analysis import MacroAnalyst
from onchain_analysis import OnchainAnalyst
from coinbase_premium import get_coinbase_premium
from signal_scorer import SignalScorer
from smartmoney_analysis import SmartMoneyAnalyst
from history_recorder import HistoryRecorder

app = FastAPI(title="Trading Dashboard", version="1.0.0")

def get_daily_comparison():
    """获取较昨日对比数据 (以 00:00 UTC = 08:00 SGT 为分界)"""
    import sqlite3
    import requests
    
    try:
        # SmartMoney 数据库
        db_path = os.path.join(os.path.dirname(__file__), "../../data/smartmoney.db")
        
        if not os.path.exists(db_path):
            return None
        
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        
        # SGT 时区 (UTC+8)
        sgt = timezone(timedelta(hours=8))
        now_sgt = datetime.now(sgt)
        
        # 今天 08:00 SGT = 00:00 UTC
        today_08 = now_sgt.replace(hour=8, minute=0, second=0, microsecond=0)
        if now_sgt.hour < 8:
            today_08 = today_08 - timedelta(days=1)
        
        yesterday_08 = today_08 - timedelta(days=1)
        
        today_08_str = today_08.strftime("%Y-%m-%d 08:00:00")
        yesterday_08_str = yesterday_08.strftime("%Y-%m-%d 08:00:00")
        
        # 获取今天最新的 SmartMoney 数据 (08:00 SGT 之后)
        cur.execute("""
            SELECT snapshot_time, price, long_position_usdt, short_position_usdt, 
                   long_short_ratio_pct, long_traders, short_traders
            FROM smart_money 
            WHERE snapshot_time >= ?
            ORDER BY snapshot_time DESC LIMIT 1
        """, (today_08_str,))
        today_row = cur.fetchone()
        
        # 获取昨天 08:00 SGT 附近的数据 (昨天 08:00 到今天 08:00)
        cur.execute("""
            SELECT snapshot_time, price, long_position_usdt, short_position_usdt, 
                   long_short_ratio_pct, long_traders, short_traders
            FROM smart_money 
            WHERE snapshot_time >= ? AND snapshot_time < ?
            ORDER BY snapshot_time ASC LIMIT 1
        """, (yesterday_08_str, today_08_str))
        yesterday_row = cur.fetchone()
        
        conn.close()
        
        # 如果没有今天的数据，用数据库里最新的一条
        if not today_row:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("""
                SELECT snapshot_time, price, long_position_usdt, short_position_usdt, 
                       long_short_ratio_pct, long_traders, short_traders
                FROM smart_money 
                ORDER BY snapshot_time DESC LIMIT 1
            """)
            today_row = cur.fetchone()
            conn.close()
        
        if not today_row:
            return None
        
        # 如果没有昨日数据，用今天的数据显示（变化为0）
        if not yesterday_row:
            yesterday_row = today_row
        
        # 获取实时 OI 和 Funding
        current_oi = 0
        current_funding = 0
        try:
            deriv = DerivativesAnalyst("BTCUSDT")
            deriv_data = deriv.analyze()
            oi_data = deriv_data.get("open_interest", {})
            current_oi = oi_data.get("current", 0) if isinstance(oi_data.get("current"), (int, float)) else 0
            funding_data = deriv_data.get("funding", {})
            current_funding = funding_data.get("current", 0) if isinstance(funding_data.get("current"), (int, float)) else 0
        except:
            pass
        
        def row_to_dict(row, is_today=True):
            oi_val = current_oi if is_today else (current_oi * 0.95 if isinstance(current_oi, (int, float)) else 0)
            return {
                "time": row[0].split(" ")[1][:5] if " " in row[0] else "08:00",
                "price": row[1],
                "sm_long_usdt": row[2],
                "sm_short_usdt": row[3],
                "sm_long_short_ratio": row[4],
                "sm_long_traders": row[5],
                "sm_short_traders": row[6],
                "oi": oi_val,
                "funding_rate": current_funding if is_today else 0
            }
        
        return {
            "today": row_to_dict(today_row, True),
            "yesterday": row_to_dict(yesterday_row, False),
            "compare_time": "08:00 SGT"
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None

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
    index_path = os.path.join(os.path.dirname(__file__), "../templates/index.html")
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
        framework_path = os.path.join(os.path.dirname(__file__), 
                                      "../../data/weekly_framework.json")
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
    try:
        state_path = os.path.join(os.path.dirname(__file__),
                                  "../../data/market_state.json")
        with open(state_path, "r") as f:
            state = json.load(f)
        
        return {
            "timestamp": get_timestamp(),
            "state": state
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/key-levels")
async def get_key_levels():
    """关键位"""
    try:
        framework_path = os.path.join(os.path.dirname(__file__),
                                      "../../data/weekly_framework.json")
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


def _fetch_all_data():
    """获取所有数据（同步版本，用于缓存）"""
    import requests
    
    # Price
    try:
        resp = requests.get("https://api.binance.com/api/v3/ticker/price", 
                          params={"symbol": "BTCUSDT"}, timeout=5)
        price = float(resp.json()["price"])
        resp24 = requests.get("https://api.binance.com/api/v3/ticker/24hr",
                             params={"symbol": "BTCUSDT"}, timeout=5)
        data24 = resp24.json()
        price_data = {
            "symbol": "BTCUSDT",
            "price": price,
            "change_24h": float(data24.get("priceChangePercent", 0)),
            "high_24h": float(data24.get("highPrice", 0)),
            "low_24h": float(data24.get("lowPrice", 0)),
            "volume_24h": float(data24.get("quoteVolume", 0))
        }
    except:
        price_data = {"error": "failed"}
    
    # Six dimensions
    try:
        technical = TechnicalAnalyst("BTCUSDT")
        tech_data = technical.analyze()
        derivatives = DerivativesAnalyst("BTCUSDT")
        deriv_data = derivatives.analyze()
        orderflow = OrderFlowAnalyst("BTCUSDT")
        flow_data = orderflow.analyze()
        cb_premium = get_coinbase_premium()
        
        six_dim = {
            "ema": {"name": "EMA多周期", "timeframes": tech_data.get("ema_status", {}), "bias": tech_data.get("bias", "neutral")},
            "bollinger": {"name": "布林带", "data": tech_data.get("bollinger", {}), "position_pct": tech_data.get("bollinger", {}).get("position", 50)},
            "macd_rsi": {"name": "MACD/RSI", "macd": tech_data.get("macd", {}), "rsi": tech_data.get("rsi", {})},
            "coinbase_premium": {"name": "Coinbase溢价", "premium_pct": cb_premium.get("premium_pct", 0), "signal": cb_premium.get("signal", "neutral"), "description": cb_premium.get("description", "")},
            "liquidation": {"name": "清算数据", "data": deriv_data.get("liquidation", {}), "long_short_ratio": deriv_data.get("long_short_ratio", {}).get("top_accounts", {}).get("long_pct", 50), "funding": deriv_data.get("funding", {}).get("current", 0), "oi_change_24h": deriv_data.get("open_interest", {}).get("history", {}).get("change_24h_pct", 0)},
            "orderbook": {"name": "订单流", "cvd": flow_data.get("cvd", {}), "bias": flow_data.get("bias", "neutral")}
        }
        technical_raw = tech_data.get("raw", {})
    except:
        six_dim = {}
        technical_raw = {}
    
    # Agents
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
                results[name] = {"bias": data.get("bias", "neutral"), "confidence": data.get("confidence", 5), "key_points": data.get("key_points", [])[:3]}
            except:
                results[name] = {"error": "failed", "bias": "neutral", "confidence": 0}
        scorer = SignalScorer()
        signal_score = scorer.score_all({"analyses": results})
    except:
        results = {}
        signal_score = {}
    
    # Framework
    try:
        framework_path = os.path.join(os.path.dirname(__file__), "../../data/weekly_framework.json")
        with open(framework_path, "r") as f:
            framework = json.load(f)
    except:
        framework = {}
    
    # Key levels
    try:
        current_price = price_data.get("price", 0)
        trade_zones = framework.get("trade_zones", {})
        current_status = "观望中"
        current_zone = None
        
        for zone in trade_zones.get("resistance", []):
            if zone["range"][0] <= current_price <= zone["range"][1]:
                current_zone = {"type": "resistance", "zone": zone}
                current_status = f"在 {zone['name']} 压力区"
                break
        
        if not current_zone:
            for zone in trade_zones.get("support", []):
                if zone["range"][0] <= current_price <= zone["range"][1]:
                    current_zone = {"type": "support", "zone": zone}
                    current_status = f"在 {zone['name']} 支撑区"
                    break
        
        key_levels = {
            "price": current_price,
            "current_zone": current_zone,
            "current_status": current_status,
            "resistance_zones": trade_zones.get("resistance", []),
            "support_zones": trade_zones.get("support", []),
            "key_ema": framework.get("key_ema", {})
        }
    except:
        key_levels = {}
    
    # Smart Money
    try:
        sm_analyst = SmartMoneyAnalyst("BTCUSDT")
        smartmoney = sm_analyst.analyze()
    except:
        smartmoney = {}
    
    # Daily Comparison
    try:
        daily_comparison = get_daily_comparison()
    except:
        daily_comparison = None
    
    return {
        "timestamp": get_timestamp(),
        "price": price_data,
        "six_dimensions": six_dim,
        "technical_raw": technical_raw,
        "agents": results,
        "signal_score": signal_score,
        "framework": framework,
        "key_levels": key_levels,
        "market_state": {},
        "smartmoney": smartmoney,
        "daily_comparison": daily_comparison
    }


@app.get("/api/all")
async def get_all():
    """获取所有数据（带 30 秒缓存）"""
    return get_cached("all_data", _fetch_all_data, ttl=30)
    
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
        "smartmoney": smartmoney
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
