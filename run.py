import sys
import subprocess
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

# ==========================================
# 1. 라이브러리 강제 설치 (Self-Healing)
# ==========================================
def install_and_import(package, pip_name=None):
    if pip_name is None:
        pip_name = package
    try:
        return __import__(package)
    except ImportError:
        print(f"📦 {pip_name} 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return __import__(package)

yf = install_and_import("yfinance")
requests = install_and_import("requests")
pd = install_and_import("pandas")
np = install_and_import("numpy")

# [핵심] 안정적인 번역기 (Deep Translator)
try:
    from deep_translator import GoogleTranslator
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
    from deep_translator import GoogleTranslator

# ==========================================
# 2. V7.1 핵심 모듈 (ETF 식별 + 로그 강화)
# ==========================================

# ETF 리스트 정의 (노이즈 관리용)
ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]

### V7 PATCH: Hard Cut (기초 체력 필터)
def check_hard_cut(ticker, hist):
    try:
        try:
            market_cap = ticker.fast_info['market_cap']
        except:
            market_cap = ticker.info.get("marketCap", 0) or 0
            
        avg_dollar_vol = (hist["Close"] * hist["Volume"]).rolling(20).mean().iloc[-1]

        # ETF는 시총 기준 예외 적용 가능하나, 일단 안전하게 포함
        if market_cap < 2_000_000_000: return False, "Small Cap"
        if avg_dollar_vol < 20_000_000: return False, "Low Liquidity"
        
        return True, "Pass"
    except:
        return False, "Data Error"

### V7 PATCH: ATR 기반 Tier 계산
def calc_atr_and_tier(hist):
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(20).mean().iloc[-1]
    cur_price = close.iloc[-1]
    
    if cur_price == 0: return 3, -35, 0, "Error"

    vol_ratio = atr / cur_price

    if vol_ratio < 0.025:
        return 1, -15, round(vol_ratio * 100, 2), "Tier 1 (Safe)"
    elif vol_ratio < 0.05:
        return 2, -25, round(vol_ratio * 100, 2), "Tier 2 (Growth)"
    else:
        return 3, -35, round(vol_ratio * 100, 2), "Tier 3 (Volatile)"

### V7 PATCH: Event Radar (거래량 + 가격 충격)
def check_event_radar(hist):
    try:
        cur_vol = hist["Volume"].iloc[-1]
        avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0

        prev_close = hist["Close"].iloc[-2]
        cur_close = hist["Close"].iloc[-1]
        price_change_pct = abs((cur_close - prev_close) / prev_close) * 100
        gap_pct = abs((hist["Open"].iloc[-1] - prev_close) / prev_close) * 100

        if vol_ratio >= 2.5 and (price_change_pct >= 4.0 or gap_pct >= 2.0):
            return True, round(vol_ratio, 2), round(price_change_pct, 2)
        
        return False, round(vol_ratio, 2), round(price_change_pct, 2)
    except:
        return False, 0, 0

# ==========================================
# 3. 메인 로직 (Brain) - 유니버스 확장 & 로그 강화
# ==========================================
def run_logic():
    print("🧠 [Brain] Hybrid Sniper V7.1 Engine 가동...")
    print("📡 레이더: 확장된 유니버스 + ETF 식별 + 정밀 로그 모드")

    # [GPT 제안 반영] 확장된 유니버스 (약 50개)
    universe = [
        # 1. 빅테크 & 우량주
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "TSLA", "NVDA", "AMD", "AVGO",
        "CRM", "ADBE", "INTC", "CSCO", "CMCSA", "PEP", "KO", "COST", "WMT", "DIS",
        # 2. 고성장 & 변동성
        "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "DKNG", "ROKU", "SQ",
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "CVNA", "U", "RBLX", "PATH", "AI",
        "IONQ", "JOBY", "ACHR", "HIMS", "ALIT",
        # 3. ETF (노이즈 체크용)
        "TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"
    ]

    survivors = []
    
    # [GPT 제안 반영] 탈락 사유 카운터 (Visibility)
    stats = {"HardCut": 0, "NotEnoughDrop": 0, "NoEvent": 0, "Error": 0, "Pass": 0}

    print(f"🔍 총 {len(universe)}개 종목 정밀 스캔 시작...\n")

    for i, sym in enumerate(universe):
        try:
            # 진행상황 표시 (줄바꿈 없이)
            print(f"   Running.. [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            
            if len(hist) < 120: 
                stats["Error"] += 1
                continue

            # 1. Hard Cut
            passed, reason = check_hard_cut(t, hist)
            if not passed:
                stats["HardCut"] += 1
                continue

            # 2. Tier & Drop
            tier, drop_limit, vol_ratio, tier_label = calc_atr_and_tier(hist)
            
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100

            if dd > drop_limit: # 낙폭 부족
                stats["NotEnoughDrop"] += 1
                continue

            # 3. Event Radar
            is_hit, vol_spike, move_pct = check_event_radar(hist)
            
            if not is_hit:
                stats["NoEvent"] += 1
                continue
            
            # === 생존 ===
            stats["Pass"] += 1
            is_etf = sym in ETF_LIST
            final_label = f"[ETF] {tier_label}" if is_etf else tier_label
            
            print(f"🎯 [HIT] {sym} 포착! ({final_label}) Vol:{vol_spike}x Drop:{round(dd,1)}%")
            
            survivors.append({
                "symbol": sym,
                "price": round(cur, 2),
                "dd": round(dd, 2),
                "tier_label": final_label,
                "radar_msg": f"Vol {vol_spike}x / Move {move_pct}%",
                "name": t.info.get("shortName", sym)
            })

        except Exception as e:
            stats["Error"] += 1
            continue

    survivors.sort(key=lambda x: x["dd"])
    
    # [GPT 제안 반영] 스캔 결과 요약 리포트 출력
    print("\n" + "="*40)
    print(f"📊 [스캔 결과 요약] 총 {len(universe)}개 중")
    print(f"   ❌ 기초체력 미달 (HardCut): {stats['HardCut']}개")
    print(f"   📉 낙폭 조건 미달 (Waiting): {stats['NotEnoughDrop']}개")
    print(f"   💤 이벤트 없음 (No Event): {stats['NoEvent']}개")
    print(f"   ✅ 최종 포착 (Survivors): {stats['Pass']}개")
    print("="*40 + "\n")
    
    return survivors

# ==========================================
# 4. 뉴스 엔진 (기존 기능 유지)
# ==========================================
def calculate_relevance_score(title_en):
    score = 0
    title_lower = title_en.lower()
    
    tier1_keywords = ['sec', 'fda', 'approved', 'dismissed', 'lawsuit', 'regulation', 'settlement', 'won', 'cleared', 'ban']
    for kw in tier1_keywords:
        if kw in title_lower: score += 10
            
    tier2_keywords = ['earnings', 'revenue', 'profit', 'surge', 'jump', 'plunge', 'crash', 'record', 'upgrade', 'downgrade']
    for kw in tier2_keywords:
        if kw in title_lower: score += 5
            
    return score

def get_google_news_rss_optimized(symbol):
    raw_news_items = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall('./channel/item')
            
            for item in items:
                title = item.find('title').text
                if " - " in title: title = title.rsplit(" - ", 1)[0]
                
                pubDate = item.find('pubDate').text
                try:
                    dt_obj = datetime.strptime(pubDate[:16], "%a, %d %b %Y")
                    date_str = dt_obj.strftime("%Y.%m.%d")
                except:
                    date_str = ""
                
                score = calculate_relevance_score(title)

                raw_news_items.append({
                    "title_en": title,
                    "link": item.find('link').text,
                    "date_str": date_str,
                    "score": score
                })
            
            raw_news_items.sort(key=lambda x: x['score'], reverse=True)
            top_news = raw_news_items[:3]
            
            translator = GoogleTranslator(source='auto', target='ko')
            final_items = []
            
            for item in top_news:
                try:
                    prefix = "★ " if item['score'] >= 10 else ""
                    translated = translator.translate(item['title_en'])
                    item['title_ko'] = prefix + translated
                except:
                    item['title_ko'] = item['title_en']
                final_items.append(item)
                
            return final_items
    except:
        return []
    return []

# ==========================================
# 5. 시각화 (ETF 뱃지 지원)
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        if sym == "NO-TARGETS":
            news_html = "<p class='no-news'>검색 조건을 만족하는 종목이 없습니다.</p>"
            news_footer = ""
        else:
            news_data = get_google_news_rss_optimized(sym)
            news_html = ""
            if news_data:
                for n in news_data:
                    news_html += f"""
                    <div class='news-item'>
                        <span class='date'>{n['date_str']}</span>
                        <a href='{n['link']}' target='_blank' title='[원문] {n['title_en']}'>
                            {n['title_ko']}
                        </a>
                    </div>
                    """
            else:
                news_html = "<p class='no-news'>관련 주요 뉴스가 없습니다.</p>"

            google_search_url = f"https://www.google.com/search?q={sym}+주식+뉴스&tbm=nws"
            news_footer = f"""
            <div class="news-footer">
                <a href="{google_search_url}" target="_blank" class="google-btn">
                    구글 뉴스 더보기 ➜
                </a>
            </div>
            """

        tier_label = stock.get('tier_label', '')
        radar_msg = stock.get('radar_msg', '')
        
        # [GPT 제안] ETF 여부에 따라 뱃지 색상 변경 (시각적 구분)
        is_etf = "[ETF]" in tier_label
        badge_bg = "#8e44ad" if is_etf else "#2c3e50" # ETF는 보라색, 일반은 네이비
        
        tier_badge = f"<span class='badge' style='background:{badge_bg}; color:#ecf0f1;'>{tier_label}</span>" if tier_label else ""
        radar_badge = f"<span class='badge' style='background:rgba(242, 54, 69, 0.15); color:#f23645;'>{radar_msg}</span>" if radar_msg else ""

        html_cards += f"""
        <div class="card">
            <div class="card-header">
                <div class="stock-info">
                    <span class="symbol">{sym}</span>
                    <span class="name">{stock.get('name', '')}</span>
                </div>
                <div class="stock-metrics">
                    <span class="price">${stock['price']:.2f}</span>
                    {tier_badge}
                    {radar_badge}
                </div>
            </div>
            <div class="card-body">
                <div class="news-section">
                    <h4>📰 주요 뉴스 (V7 Radar)</h4>
                    <div class="news-list">
                        {news_html}
                    </div>
                    {news_footer}
                </div>
                <div class="chart-section">
                    <div class="tradingview-widget-container" style="height:100%;width:100%">
                        <div id="{chart_id}" style="height:400px;width:100%"></div>
                        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                        <script type="text/javascript">
                        new TradingView.widget({{
                            "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC",
                            "theme": "dark", "style": "1", "locale": "kr", "toolbar_bg": "#1e222d",
                            "enable_publishing": false, "hide_side_toolbar": false,
                            "container_id": "{chart_id}"
                        }});
                        </script>
                    </div>
                </div>
            </div>
        </div>
        """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Hybrid Sniper V7.1 Terminal</title>
        <style>
            :root {{
                --bg-color: #131722; --card-bg: #1e222d; --text-main: #d1d4dc;
                --text-sub: #787b86; --accent-red: #f23645; --accent-blue: #2962ff;
                --border-color: #2a2e39;
            }}
            body {{ font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg-color); color: var(--text-main); padding: 40px 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; margin-bottom: 40px; color: #fff; letter-spacing: 2px; }}
            .card {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
            .card-header {{ padding: 20px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }}
            .symbol {{ font-size: 1.8em; font-weight: 700; color: #fff; margin-right: 10px; }}
            .name {{ color: var(--text-sub); font-size: 0.9em; }}
            .price {{ font-size: 1.5em; font-weight: 600; color: #fff; margin-right: 15px; }}
            .badge {{ padding: 5px 10px; border-radius: 4px; font-weight: bold; font-size: 0.8em; margin-left: 5px; border: 1px solid #444; }}
            .card-body {{ display: flex; flex-wrap: wrap; height: 450px; }}
            .news-section {{ flex: 1; min-width: 300px; padding: 20px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; background: #1e222d; }}
            .news-list {{ flex-grow: 1; overflow-y: auto; }}
            .news-item {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }}
            .news-item:last-child {{ border-bottom: none; }}
            .news-item a {{ color: var(--text-main); text-decoration: none; font-size: 0.95em; display: block; margin-top: 4px; line-height: 1.4; }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            .date {{ font-size: 0.75em; color: var(--text-sub); display: block; margin-bottom: 4px; }}
            .no-news {{ color: var(--text-sub); font-style: italic; }}
            .news-footer {{ padding-top: 15px; border-top: 1px solid var(--border-color); text-align: center; }}
            .google-btn {{ background: #2a2e39; color: #fff; padding: 8px 16px; border-radius: 20px; text-decoration: none; font-size: 0.85em; transition: 0.3s; display: inline-block; }}
            .google-btn:hover {{ background: var(--accent-blue); }}
            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            @media (max-width: 768px) {{ .card-body {{ height: auto; }} .news-section {{ border-right: none; border-bottom: 1px solid var(--border-color); }} .chart-section {{ height: 400px; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>HYBRID SNIPER <span style="font-size:0.5em; color:#4cd137;">V7.1</span></h1>
            {html_cards}
        </div>
    </body>
    </html>
    """
    
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

if __name__ == "__main__":
    targets = run_logic()
    
    # 0개일 경우 처리
    if not targets:
        print("💡 결과가 0개입니다. '탐지 없음' 보고서를 생성합니다.")
        targets = [{
            "symbol": "NO-TARGETS", 
            "price": 0.00, 
            "dd": 0.00, 
            "name": "탐지된 종목이 없습니다 (엄격한 조건)", 
            "tier_label": "System Info", 
            "radar_msg": "Universe scanned"
        }]
    
    generate_dashboard(targets)
    abs_path = os.path.abspath('data/artifacts/dashboard/index.html')
    print(f"\n✅ 작전 완료. 보고서 생성됨: \n👉 {abs_path}")
