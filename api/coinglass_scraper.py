#!/usr/bin/env python3
"""
Coinglass 数据爬虫 - 抓取清算数据
"""

import json
import re
import time
from datetime import datetime

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


def scrape_liquidation_data():
    """抓取清算数据"""
    if not SELENIUM_AVAILABLE:
        return {"error": "需要安装 selenium: pip install selenium", "success": False}
    
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
        
        # 解析数据
        result = {
            "timestamp": datetime.now().isoformat(),
            "source": "coinglass",
            "success": True
        }
        
        # 24H 爆仓
        match_24h = re.search(r'24h Rekt\s*\$?([\d.]+[KMB]?)\s*Long\s*\$?([\d.]+[KMB]?)\s*Short\s*\$?([\d.]+[KMB]?)', page_text)
        if match_24h:
            result["liquidation_24h"] = {
                "total": parse_value(match_24h.group(1)),
                "long": parse_value(match_24h.group(2)),
                "short": parse_value(match_24h.group(3))
            }
        
        # 4H 爆仓
        match_4h = re.search(r'4h Rekt\s*\$?([\d.]+[KMB]?)\s*Long\s*\$?([\d.]+[KMB]?)\s*Short\s*\$?([\d.]+[KMB]?)', page_text)
        if match_4h:
            result["liquidation_4h"] = {
                "total": parse_value(match_4h.group(1)),
                "long": parse_value(match_4h.group(2)),
                "short": parse_value(match_4h.group(3))
            }
        
        # 1H 爆仓
        match_1h = re.search(r'1h Rekt\s*\$?([\d.]+[KMB]?)\s*Long\s*\$?([\d.]+[KMB]?)\s*Short\s*\$?([\d.]+[KMB]?)', page_text)
        if match_1h:
            result["liquidation_1h"] = {
                "total": parse_value(match_1h.group(1)),
                "long": parse_value(match_1h.group(2)),
                "short": parse_value(match_1h.group(3))
            }
        
        # BTC 24H 爆仓
        btc_match = re.search(r'BTC\s*\$[\d,]+\s*[+-]?[\d.]+%\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)\s*\$?([\d.]+[KMB]?)', page_text)
        if btc_match:
            result["btc_liquidation"] = {
                "1h_long": parse_value(btc_match.group(1)),
                "1h_short": parse_value(btc_match.group(2)),
                "4h_long": parse_value(btc_match.group(3)),
                "4h_short": parse_value(btc_match.group(4)),
                "12h_long": parse_value(btc_match.group(5)),
                "12h_short": parse_value(btc_match.group(6)),
                "24h_long": parse_value(btc_match.group(7)),
                "24h_short": parse_value(btc_match.group(8))
            }
        
        # 计算信号
        if "liquidation_24h" in result:
            liq = result["liquidation_24h"]
            total = liq["total"]
            long_pct = liq["long"] / total * 100 if total > 0 else 50
            short_pct = liq["short"] / total * 100 if total > 0 else 50
            
            # 判断信号
            if total > 1_000_000_000:  # > $1B
                result["signal"] = "极端行情"
                result["signal_level"] = "extreme"
            elif total > 500_000_000:  # > $500M
                result["signal"] = "高波动"
                result["signal_level"] = "high"
            elif total > 200_000_000:  # > $200M
                result["signal"] = "中等波动"
                result["signal_level"] = "medium"
            else:
                result["signal"] = "正常"
                result["signal_level"] = "normal"
            
            # 多空被清洗比例
            if short_pct > 70:
                result["bias"] = "bullish"
                result["bias_note"] = f"空头被清洗 ({short_pct:.1f}%)"
            elif long_pct > 70:
                result["bias"] = "bearish"
                result["bias_note"] = f"多头被清洗 ({long_pct:.1f}%)"
            else:
                result["bias"] = "neutral"
                result["bias_note"] = f"多空均衡 ({long_pct:.1f}% / {short_pct:.1f}%)"
        
        return result
        
    except Exception as e:
        return {"error": str(e), "success": False}
    finally:
        if driver:
            driver.quit()


def format_output(data):
    """格式化输出"""
    if not data.get("success"):
        return f"❌ 爬取失败: {data.get('error', 'Unknown error')}"
    
    lines = []
    lines.append("📊 Coinglass 清算数据")
    lines.append(f"⏰ {data['timestamp']}")
    lines.append("")
    
    if "liquidation_24h" in data:
        liq = data["liquidation_24h"]
        lines.append(f"**24H 爆仓**: ${liq['total']/1e6:.2f}M")
        lines.append(f"  • 多头: ${liq['long']/1e6:.2f}M")
        lines.append(f"  • 空头: ${liq['short']/1e6:.2f}M")
    
    if "liquidation_1h" in data:
        liq = data["liquidation_1h"]
        lines.append(f"**1H 爆仓**: ${liq['total']/1e6:.2f}M")
    
    if "btc_liquidation" in data:
        btc = data["btc_liquidation"]
        lines.append("")
        lines.append("**BTC 清算**:")
        lines.append(f"  • 24H: 多 ${btc['24h_long']/1e6:.2f}M / 空 ${btc['24h_short']/1e6:.2f}M")
        lines.append(f"  • 1H: 多 ${btc['1h_long']/1e3:.1f}K / 空 ${btc['1h_short']/1e3:.1f}K")
    
    if "signal" in data:
        lines.append("")
        lines.append(f"📈 信号: {data['signal']}")
        lines.append(f"📊 偏向: {data.get('bias_note', '-')}")
    
    return "\n".join(lines)


if __name__ == "__main__":
    print("正在爬取 Coinglass 数据...")
    result = scrape_liquidation_data()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("\n" + "="*50 + "\n")
    print(format_output(result))
