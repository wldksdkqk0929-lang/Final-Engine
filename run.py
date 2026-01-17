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
# 2. V7 PATCH - 핵심 모듈 함수 (GPT Logic Applied)
# ==========================================

### V7 PATCH: Hard Cut (기초 체력 필터)
def check_hard_cut(ticker, hist):
    try:
        # 속도 최적화를 위해 fast_info 사용 권장, 실패시 info 사용
        try:
            market_cap = ticker.fast_info['market_cap']
        except:
            market_cap = ticker.info.get("marketCap", 0) or 0
            
        # 20일 평균 거래대금 계산
        avg_dollar_vol = (hist["Close"] * hist["Volume"]).rolling(20).mean().iloc[-1]

        if market_cap < 2_000_000_000:   # 시총 $2B 미만 탈락
            return False
        if avg_dollar_vol < 20_000_000: # 거래대금 $20M 미만 탈락
            return False
        return True
    except:
        return False

### V7 PATCH: ATR 기반 Tier 계산
def calc_atr_and_tier(hist):
    high = hist["High"]
    low = hist["Low"]
    close = hist["Close"]

    # True Range 계산
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR(20) 및 변동성 비율
    atr = tr.rolling(20).mean().iloc[-1]
    cur_price = close.iloc[-1]
    
    if cur_price == 0: return 3, -35, 0 # 에러 방지

    vol_ratio = atr / cur_price

    # Tier 분류 (변동성에 따라 낙폭 기준 차등 적용)
    if vol_ratio < 0.025:
        tier = 1
        drop_threshold = -15
        label = "Tier 1 (Safe)"
    elif vol_ratio < 0.05:
        tier = 2
        drop_threshold = -25
        label = "Tier 2 (Growth)"
    else:
        tier = 3
        drop_threshold = -35
        label = "Tier 3 (Volatile)"

    return tier, drop_threshold, round(vol_ratio * 100, 2), label

### V7 PATCH: Event Radar (거래량 + 가격 충격)
def check_event_radar(hist):
    try:
        cur_vol = hist["Volume"].iloc[-1]
        avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
        
        # 거래량 비율 (평소 대비 몇 배인가)
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0

        prev_close = hist["Close"].iloc[-2]
        cur_close = hist["Close"].iloc[-1]
        
        # 가격 등락률 (절대값)
        price_change_pct = abs((cur_close - prev_close) / prev_close) * 100
        
        # 갭 하락률
        gap_pct = abs((hist["Open"].iloc[-1] - prev_close) / prev_close) * 100

        # Composite Signature (복합 신호 탐지)
        # 거래량 2.5배 이상 터지고 AND (가격이 4% 이상 움직이거나 OR 갭이 2% 이상 발생)
        if vol_ratio >= 2.5 and (price_change_pct >= 4.0 or gap_pct >= 2.0):
            return True, round(vol_ratio, 2), round(price_change_pct, 2), round(gap_pct, 2)

        return False, round(vol_ratio, 2), round(price_change_pct, 2), round(gap_pct, 2)

    except:
        return False, 0, 0, 0

# ==========================================
# 3. 메인 로직 (Brain) - V7 엔진 가동
# ==========================================
def run_logic():
    print("🧠 [Brain] Hybrid Sniper V7 Radar Engine 가동...")
    print("📡 레이더: 유동성 필터 + 가변 낙폭 + 이벤트 탐지 중...")

    # 분석 대상 유니버스 (확장 권장)
    universe = [
        "MARA", "LCID", "TSLA", "INTC", "PLTR", "SOFI", "AMD", "NVDA", 
        "RIVN", "OPEN", "IONQ", "JOBY", "UPST", "AFRM", "COIN", "MSTR", "CVNA",
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX"
    ]

    survivors = []

    for sym in universe:
        try:
            print(f"analyzing.. {sym}", end="\r")
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            
            if len(hist) < 120: continue # 최소 데이터 확보

            # === [Step 1] Hard Cut (기초 체력) ===
            if not check_hard_cut(t, hist):
                continue

            # === [Step 2] Tier 계산 (목표 설정) ===
            tier, drop_threshold, vol_ratio, tier_label = calc_atr_and_tier(hist)

            # === [Step 3] Drawdown 계산 (120일 고점 기준) ===
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100

            # 낙폭 조건 미달 시 탈락 (예: -10% 인데 기준이 -15%면 탈락)
            # dd는 음수이므로, dd > drop_threshold (예: -10 > -15) 이면 아직 덜 떨어진 것
            if dd > drop_threshold:
                continue

            # === [Step 4] Event Radar (사건 탐지) ===
            radar_hit, vol_spike, price_impulse, gap_impulse = check_event_radar(hist)
            
            if not radar_hit:
                continue
            
            # === [Step 5] 최종 생존 ===
            print(f"🎯 [HIT] {sym} 포착! ({tier_label}) Vol:{vol_spike}x Drop:{round(dd,1)}%")
            
            survivors.append({
                "symbol": sym,
                "price": round(cur, 2),
                "dd": round(dd, 2),
                "tier": tier,
                "tier_label": tier_label,
                "volatility_pct": vol_ratio,
                "vol_spike": vol_spike,
                "radar_msg": f"Vol {vol_spike}x / Move {price_impulse}%",
                "name": t.info.get("shortName", sym)
            })

        except Exception as e:
            # print(f"⚠️ {sym} 처리 오류: {e}")
            continue

    survivors.sort(key=lambda x: x["dd"])
    print(f"\n⚔️ 최종 포착 종목: {len(survivors)}개")
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
    # print(f"📰 {symbol} 뉴스 수집 중...")
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

    except Exception:
        return []
    
    return []

# ==========================================
# 5. 시각화 (대시보드 생성)
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
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

        # V7 정보 표시 (Tier, Radar Msg)
        tier_label = stock.get('tier_label', 'Tier ?')
        radar_msg = stock.get('radar_msg', 'Detected')
        
        tier_badge = f"<span class='badge' style='background:#2c3e50; color:#ecf0f1;'>{tier_label}</span>"
        radar_badge = f"<span class='badge' style='background:rgba(242, 54, 69, 0.15); color:#f23645;'>{radar_msg}</span>"

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
        <title>Hybrid Sniper V7.0 Terminal</title>
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
            <h1>HYBRID SNIPER <span style="font-size:0.5em; color:#4cd137;">V7.0</span></h1>
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
    
    if targets:
        generate_dashboard(targets)
        print("✅ 작전 완료. 대시보드(index.html)가 생성되었습니다.")
    else:
        print("\n⚠️ 탐지된 종목이 없습니다.")
