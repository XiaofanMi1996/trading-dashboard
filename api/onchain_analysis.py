#!/usr/bin/env python3
"""
Onchain Analyst - 链上分析脚本
数据源: 免费公开 API (有限)
"""

import requests
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

class OnchainAnalyst:
    def __init__(self):
        pass
    
    def get_exchange_balance(self) -> Dict[str, Any]:
        """获取交易所余额估算 (通过公开数据)"""
        # 使用 blockchain.info 获取一些基础数据
        # 注: 完整数据需要 Glassnode/CryptoQuant 付费
        
        try:
            # 获取 BTC 总供应量和流通数据
            url = "https://blockchain.info/q/totalbc"
            resp = requests.get(url, timeout=10)
            total_supply = int(resp.text) / 1e8  # satoshi to BTC
            
            # 估算交易所余额 (基于历史比例，约15-17%)
            # 这是简化估算，实际需要付费数据
            estimated_exchange_pct = 15.5
            estimated_exchange_btc = total_supply * (estimated_exchange_pct / 100)
            
            return {
                "total_supply_btc": round(total_supply, 0),
                "estimated_exchange_btc": round(estimated_exchange_btc, 0),
                "estimated_exchange_pct": estimated_exchange_pct,
                "note": "估算值，精确数据需 Glassnode"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_mempool_status(self) -> Dict[str, Any]:
        """获取内存池状态"""
        try:
            url = "https://mempool.space/api/mempool"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            count = data.get("count", 0)
            vsize = data.get("vsize", 0)
            total_fee = data.get("total_fee", 0)
            
            # 拥堵判断
            if count > 100000:
                congestion = "严重拥堵"
            elif count > 50000:
                congestion = "中度拥堵"
            elif count > 20000:
                congestion = "轻度拥堵"
            else:
                congestion = "畅通"
            
            return {
                "tx_count": count,
                "vsize_mb": round(vsize / 1e6, 2),
                "total_fee_btc": round(total_fee / 1e8, 4),
                "congestion": congestion
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_fee_estimates(self) -> Dict[str, Any]:
        """获取手续费估算"""
        try:
            url = "https://mempool.space/api/v1/fees/recommended"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            
            return {
                "fastest_sat_vb": data.get("fastestFee", 0),
                "half_hour_sat_vb": data.get("halfHourFee", 0),
                "hour_sat_vb": data.get("hourFee", 0),
                "economy_sat_vb": data.get("economyFee", 0)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_hashrate(self) -> Dict[str, Any]:
        """获取算力数据"""
        try:
            url = "https://blockchain.info/q/hashrate"
            resp = requests.get(url, timeout=10)
            hashrate_ths = float(resp.text)  # TH/s
            hashrate_eh = hashrate_ths / 1e6  # EH/s
            
            return {
                "hashrate_eh": round(hashrate_eh, 2),
                "status": "正常" if hashrate_eh > 500 else "偏低"
            }
        except Exception as e:
            return {"error": str(e)}
    
    def get_difficulty(self) -> Dict[str, Any]:
        """获取难度数据"""
        try:
            url = "https://blockchain.info/q/getdifficulty"
            resp = requests.get(url, timeout=10)
            difficulty = float(resp.text)
            difficulty_t = difficulty / 1e12  # T
            
            return {
                "difficulty_t": round(difficulty_t, 2)
            }
        except Exception as e:
            return {"error": str(e)}
    
    def analyze(self) -> Dict[str, Any]:
        """运行完整分析"""
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        
        # 获取数据
        exchange = self.get_exchange_balance()
        mempool = self.get_mempool_status()
        fees = self.get_fee_estimates()
        hashrate = self.get_hashrate()
        difficulty = self.get_difficulty()
        
        # 由于链上深度数据需要付费，这里主要基于网络状态判断
        # 综合判断偏中性
        bias = "neutral"
        confidence = 5
        
        key_points = []
        
        # 内存池状态
        if "congestion" in mempool:
            key_points.append(f"内存池: {mempool['congestion']} ({mempool.get('tx_count', 0):,} 笔待确认)")
        
        # 手续费
        if "fastest_sat_vb" in fees:
            key_points.append(f"手续费: {fees['fastest_sat_vb']} sat/vB (最快)")
        
        # 算力
        if "hashrate_eh" in hashrate:
            key_points.append(f"算力: {hashrate['hashrate_eh']} EH/s")
        
        # 注意事项
        alerts = []
        if mempool.get("tx_count", 0) > 100000:
            alerts.append("⚠️ 内存池严重拥堵，链上转账可能延迟")
        
        return {
            "agent": "onchain",
            "timestamp": timestamp,
            "bias": bias,
            "confidence": confidence,
            "exchange_balance": exchange,
            "mempool": mempool,
            "fees": fees,
            "hashrate": hashrate,
            "difficulty": difficulty,
            "key_points": key_points,
            "alerts": alerts,
            "note": "完整链上分析 (交易所流量/巨鲸/MVRV) 需要 Glassnode 或 CryptoQuant 付费订阅"
        }


def main():
    analyst = OnchainAnalyst()
    result = analyst.analyze()
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
