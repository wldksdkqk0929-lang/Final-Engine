import sys
import subprocess
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ==========================================
# 1. 라이브러리 설정
# ==========================================
def install_and_import(package, pip_name=None):
    if pip_name is None: pip_name = package
    try:
        return __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return __import__(package)

yf = install_and_import("yfinance")
requests = install_and_import("requests")
pd = install_and_import("pandas")
np = install_and_import("numpy")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
    from deep_translator import GoogleTranslator

# ETF 리스트
ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]

# ==========================================
# 2. V7.5 핵심 모듈 (타임머신 로직 추가)
# ==========================================

### [NEW] 타임머신 날짜 계산기
def detect_phase_dates(hist):
    try:
        # 데이터가 너무 적으면 계산 불가
        if len(hist) < 60: return None, None
        
        # 1. Phase A (Crash): 최근 6개월 중 가장 큰 낙폭(장대음봉)이 발생한 날
        # (단순 하락률뿐만 아니라 거래량도 고려하면 좋으나, 일단 하락률 우선)
        hist['Daily_Change'] = hist['Close'].pct_change()
        
        # 최근 120일(약 6개월) 데이터만 대상
        recent = hist.tail(120)
        
        # 가장 큰 하락(최소값)이 발생한 날짜
        crash_date_idx = recent['Daily_Change'].idxmin()
        crash_date = crash_date_idx.strftime("%Y-%m-%d")
        
        # 2. Phase B (Rebound): 최근 20일 중 최저점을 찍은 날 (바닥)
        # (바닥을 찍고 턴어라운드 하려는 시점이므로 최저점 날짜가 중요)
        latest_20 = hist.tail(20)
        rebound_date_idx = latest_20['Close'].idxmin()
        rebound_date = rebound_date_idx.strftime("%Y-%m-%d")
        
        return crash_date, rebound_date
        
    except Exception as e:
        return None, None

def check_hard_cut(ticker, hist):
    try:
        try: market_cap = ticker.fast_info['market_cap']
        except: market_cap = ticker.info.get("marketCap", 0) or 0
        avg_dollar_vol = (hist["Close"] * hist["Volume"]).rolling(20).mean().iloc[-1]
        
        if market_cap < 2_000_000_000: return False, "Small Cap"
        if avg_dollar_vol < 20_000_000: return False, "Low Liquidity"
        return True, "Pass"
    except: return False, "Data Error"

def calc_atr_and_tier(hist):
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(20).mean().iloc[-1]
    cur_price = close.iloc[-1]
    
    if cur_price == 0: return 3, -35, 0, "Error"
    vol_ratio = atr / cur_price

    if vol_ratio < 0.025: return 1, -15, round(vol_ratio * 100, 2), "Tier 1 (Safe)"
    elif vol_ratio < 0.05: return 2, -25, round(vol_ratio * 100, 2), "Tier 2 (Growth)"
    else: return 3, -35, round(vol_ratio * 100, 2), "Tier 3 (Volatile)"

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
    except: return False, 0, 0

# ==========================================
# 3. 메인 로직
# ==========================================
def run_logic():
    print("🧠 [Brain] Hybrid Sniper V7.5 (TimeMachine) 가동...")
    
    universe = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "TSLA", "NVDA", "AMD", "AVGO",
        "CRM", "ADBE", "INTC", "CSCO", "CMCSA", "PEP", "KO", "COST", "WMT", "DIS",
        "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "DKNG", "ROKU", "SQ",
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "CVNA", "U", "RBLX", "PATH", "AI",
        "IONQ", "JOBY", "ACHR", "HIMS", "ALIT",
        "TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"
    ]

    survivors = []
    stats = {"HardCut": 0, "NotEnoughDrop": 0, "NoEvent": 0, "Error": 0, "Pass": 0}

    print(f"🔍 총 {len(universe)}개 종목 분석 중...\n")

    for i, sym in enumerate(universe):
        try:
            print(f"   Running.. [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            
            if len(hist) < 120: 
                stats["Error"] += 1
                continue

            passed, reason = check_hard_cut(t, hist)
            if not passed:
                stats["HardCut"] += 1
                continue

            tier, drop_limit, vol_ratio, tier_label = calc_atr_and_tier(hist)
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100

            if dd > drop_limit:
                stats["NotEnoughDrop"] += 1
                continue

            is_hit, vol_spike, move_pct = check_event_radar(hist)
            if not is_hit:
                stats["NoEvent"] += 1
                continue
            
            # [NEW] 타임머신 날짜 계산
            crash_date, rebound_date = detect_phase_dates(hist)

            stats["Pass"] += 1
            is_etf = sym in ETF_LIST
            final_label = f"[ETF] {tier_label}" if is_etf else tier_label
            
            print(f"🎯 [HIT] {sym} 포착! ({final_label})")
            
            survivors.append({
                "symbol": sym,
                "price": round(cur, 2),
                "dd": round(dd, 2),
                "tier_label": final_label,
                "radar_msg": f"Vol {vol_spike}x / Move {move_pct}%",
                "name": t.info.get("shortName", sym),
                "crash_date": crash_date,    # 폭락일
                "rebound_date": rebound_date # 반등일
            })

        except Exception as e:
            stats["Error"] += 1
            continue

    survivors.sort(key=lambda x: x["dd"])
    
    print("\n" + "="*40)
    print(f"📊 [스캔 결과] 총 {len(universe)}개 중")
    print(f"   ❌ 기초체력 미달: {stats['HardCut']}")
    print(f"   📉 낙폭 조건 미달: {stats['NotEnoughDrop']}")
    print(f"   💤 이벤트 없음: {stats['NoEvent']}")
    print(f"   ✅ 최종 포착: {stats['Pass']}")
    print("="*40 + "\n")
    
    return survivors

# ==========================================
# 4. 뉴스 엔진 (최신 뉴스만 자동)
# ==========================================
def calculate_relevance_score(title_en):
    score = 0
    title_lower = title_en.lower()
    tier1 = ['sec', 'fda', 'approved', 'lawsuit', 'regulation', 'settlement', 'won', 'ban', 'earnings', 'revenue']
    for kw in tier1: 
        if kw in title_lower: score += 10
    return score

def get_google_news_rss_optimized(symbol):
    raw_news = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=5) # 타임아웃 단축
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall('./channel/item')[:5]: # 최대 5개만 파싱
                title = item.find('title').text
                if " - " in title: title = title.rsplit(" - ", 1)[0]
                pubDate = item.find('pubDate').text
                try: date_str = datetime.strptime(pubDate[:16], "%a, %d %b %Y").strftime("%Y.%m.%d")
                except: date_str = ""
                raw_news.append({"title_en": title, "link": item.find('link').text, "date_str": date_str, "score": calculate_relevance_score(title)})
            
            raw_news.sort(key=lambda x: x['score'], reverse=True)
            top_news = raw_news[:2] # 상위 2개만 번역 (부하 방지)
            
            translator = GoogleTranslator(source='auto', target='ko')
            for item in top_news:
                try: item['title_ko'] = translator.translate(item['title_en'])
                except: item['title_ko'] = item['title_en']
            return top_news
    except: return []
    return []

# ==========================================
# 5. 시각화 (타임머신 UI 적용)
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        # 1. 최신 뉴스 (자동)
        if sym == "NO-TARGETS":
            news_html = "<p class='no-news'>탐지된 종목이 없습니다.</p>"
        else:
            news_data = get_google_news_rss_optimized(sym)
            news_html = ""
            if news_data:
                for n in news_data:
                    news_html += f"<div class='news-item'><span class='date'>{n['date_str']}</span><a href='{n['link']}' target='_blank'>{n['title_ko']}</a></div>"
            else:
                news_html = "<p class='no-news'>최근 주요 뉴스가 없습니다.</p>"

        # 2. 타임머신 링크 생성 (구글 검색 URL 조합)
        # 검색어 예시: "TSLA stock news" + 날짜 필터
        crash_date = stock.get('crash_date', '')
        rebound_date = stock.get('rebound_date', '')
        
        tm_html = ""
        if crash_date and rebound_date:
            # 구글 검색 날짜 필터 URL 생성 로직
            # tbs=cdr:1,cd_min:MM/DD/YYYY,cd_max:MM/DD/YYYY
            def make_google_url(query, date_str):
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    # 전후 3일 검색
                    start = (dt - timedelta(days=2)).strftime("%m/%d/%Y")
                    end = (dt + timedelta(days=2)).strftime("%m/%d/%Y")
                    return f"https://www.google.com/search?q={sym}+stock+news&tbs=cdr:1,cd_min:{start},cd_max:{end}&tbm=nws"
                except: return "#"

            crash_url = make_google_url(sym, crash_date)
            rebound_url = make_google_url(sym, rebound_date)

            tm_html = f"""
            <div class="timemachine-box">
                <div class="tm-item crash">
                    <span class="tm-label">🔴 폭락 원인 확인</span>
                    <span class="tm-date">{crash_date}</span>
                    <a href="{crash_url}" target="_blank" class="tm-btn">뉴스 검색 ➜</a>
                </div>
                <div class="tm-item rebound">
                    <span class="tm-label">🟢 반등/바닥 확인</span>
                    <span class="tm-date">{rebound_date}</span>
                    <a href="{rebound_url}" target="_blank" class="tm-btn">뉴스 검색 ➜</a>
                </div>
            </div>
            """

        tier_label = stock.get('tier_label', '')
        radar_msg = stock.get('radar_msg', '')
        is_etf = "[ETF]" in tier_label
        badge_bg = "#8e44ad" if is_etf else "#2c3e50"
        
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
                <div class="left-section">
                    <div class="news-section">
                        <h4>📰 최신 뉴스 (Live)</h4>
                        <div class="news-list">{news_html}</div>
                    </div>
                    {tm_html}
                </div>
                <div class="chart-section">
                    <div class="tradingview-widget-container" style="height:100%;width:100%">
                        <div id="{chart_id}" style="height:100%;width:100%"></div>
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
        <title>Hybrid Sniper V7.5 (TimeMachine)</title>
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
            
            .card-body {{ display: flex; flex-wrap: wrap; height: 500px; }}
            .left-section {{ flex: 1; min-width: 320px; padding: 20px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; }}
            
            .news-section {{ flex-grow: 1; overflow-y: auto; margin-bottom: 20px; }}
            .news-item {{ margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #2a2e39; }}
            .news-item a {{ color: var(--text-main); text-decoration: none; font-size: 0.9em; display: block; line-height: 1.4; }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            .date {{ font-size: 0.75em; color: var(--text-sub); display: block; margin-bottom: 2px; }}
            .no-news {{ color: var(--text-sub); font-style: italic; font-size: 0.9em; }}

            /* 타임머신 스타일 */
            .timemachine-box {{ border-top: 1px solid var(--border-color); padding-top: 15px; }}
            .tm-item {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; padding: 8px; border-radius: 6px; }}
            .tm-item.crash {{ background: rgba(242, 54, 69, 0.1); border: 1px solid rgba(242, 54, 69, 0.3); }}
            .tm-item.rebound {{ background: rgba(38, 166, 154, 0.1); border: 1px solid rgba(38, 166, 154, 0.3); }}
            .tm-label {{ font-size: 0.8em; font-weight: bold; }}
            .tm-date {{ font-size: 0.85em; color: #fff; }}
            .tm-btn {{ background: #2a2e39; color: var(--text-main); padding: 4px 10px; border-radius: 4px; text-decoration: none; font-size: 0.75em; }}
            .tm-btn:hover {{ background: #fff; color: #000; }}

            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            @media (max-width: 768px) {{ .card-body {{ height: auto; }} .left-section {{ border-right: none; border-bottom: 1px solid var(--border-color); }} .chart-section {{ height: 400px; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V7.5 <span style="font-size:0.5em; color:#3498db;">TIMEMACHINE</span></h1>
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
    if not targets:
        print("💡 결과가 0개입니다. 더미 리포트를 생성합니다.")
        targets = [{"symbol": "NO-TARGETS", "price": 0.00, "dd": 0.00, "name": "탐지된 종목이 없습니다", "tier_label": "System Info", "radar_msg": "Universe scanned"}]
    generate_dashboard(targets)
    print(f"\n✅ V7.5 작전 완료.")
