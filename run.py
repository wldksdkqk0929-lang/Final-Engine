import sys
import subprocess
import os
import logging
from datetime import datetime

# ==========================================
# 1. 라이브러리 강제 설치 (Self-Healing)
# ==========================================
def install_and_import(package):
    try:
        return __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return __import__(package)

yf = install_and_import("yfinance")
requests = install_and_import("requests") # 요청 조작용 필수
yaml = install_and_import("yaml")

# ==========================================
# 🚨 [핵심 변경] 야후 차단 우회용 세션 생성기
# ==========================================
def get_safe_session():
    """
    깃허브 액션(서버) IP 차단을 피하기 위해
    일반 크롬 브라우저인 척 위장하는 세션을 만듭니다.
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,ko;q=0.8'
    })
    return session

# ==========================================
# 2. 로직: 낙폭 과대주 선별 (Brain)
# ==========================================
def run_logic():
    print("🧠 [Brain] 낙폭 과대주 분석 엔진 가동...")
    
    # 분석 대상 (변동성 큰 기술/성장주)
    universe = ["MARA", "LCID", "TSLA", "INTC", "PLTR", "SOFI", "AMD", "NVDA", "RIVN", "OPEN", "IONQ", "JOBY"]
    
    survivors = []
    print(f"🔍 {len(universe)}개 종목 스캔 중...")
    
    # [중요] 세션 적용: 이제부터 야후는 우리를 '브라우저'로 인식합니다.
    safe_session = get_safe_session()
    
    for sym in universe:
        try:
            # session 파라미터 추가
            t = yf.Ticker(sym, session=safe_session)
            
            hist = t.history(period="1y")
            if len(hist) < 20: continue
            
            high = hist['High'].max()
            cur = hist['Close'].iloc[-1]
            dd = ((cur - high) / high) * 100
            
            if dd < -40:
                survivors.append({
                    "symbol": sym,
                    "price": cur,
                    "dd": round(dd, 2),
                    "name": t.info.get('shortName', sym)
                })
        except:
            continue
            
    print(f"⚔️ 최종 생존 종목: {len(survivors)}개")
    return survivors

# ==========================================
# 3. 시각화: 뉴스 수집 로직 강화
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    safe_session = get_safe_session() # 여기서도 안전 세션 사용
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        # --- [뉴스 데이터 처리] ---
        news_html = ""
        try:
            # 1. 안전 세션으로 접속 시도
            t = yf.Ticker(sym, session=safe_session)
            raw_news = t.news
            
            # 2. 데이터가 비어있다면(차단됨), 검색 URL을 대신 표시
            if not raw_news:
                print(f"⚠️ {sym}: 야후 뉴스 리스트가 비어있습니다. (IP 차단 가능성)")
            
            if raw_news:
                count = 0
                for n in raw_news:
                    if count >= 3: break
                    
                    title = n.get('title', n.get('headline', ''))
                    link = n.get('link', f"https://finance.yahoo.com/quote/{sym}")
                    
                    # 날짜 처리
                    ts = n.get('providerPublishTime', 0)
                    date_str = datetime.fromtimestamp(ts).strftime('%Y.%m.%d') if ts > 0 else ""
                    
                    if title:
                        news_html += f"""
                        <div class='news-item'>
                            <span class='date'>{date_str}</span>
                            <a href='{link}' target='_blank'>{title}</a>
                        </div>
                        """
                        count += 1
            
            if not news_html: 
                news_html = "<p class='no-news'>야후 파이낸스 수신 대기중 (하단 구글 버튼 이용)</p>"

        except Exception as e:
            print(f"❌ {sym} 뉴스 에러: {e}")
            news_html = f"<p class='no-news'>뉴스 로딩 실패</p>"

        # 구글 뉴스 버튼
        google_search_url = f"https://www.google.com/search?q={sym}+stock+news&tbm=nws"
        news_footer = f"""
        <div class="news-footer">
            <a href="{google_search_url}" target="_blank" class="google-btn">
                🔍 Google News 실시간 검색
            </a>
        </div>
        """

        # --- [HTML 조립] ---
        html_cards += f"""
        <div class="card">
            <div class="card-header">
                <div class="stock-info">
                    <span class="symbol">{sym}</span>
                    <span class="name">{stock.get('name', '')}</span>
                </div>
                <div class="stock-metrics">
                    <span class="price">${stock['price']:.2f}</span>
                    <span class="badge">{stock['dd']}%</span>
                </div>
            </div>
            <div class="card-body">
                <div class="news-section">
                    <h4>NEWS BRIEFING</h4>
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

    # --- [전체 HTML] ---
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sniper Dark Terminal</title>
        <style>
            :root {{
                --bg-color: #131722; --card-bg: #1e222d; --text-main: #d1d4dc;
                --text-sub: #787b86; --accent-red: #f23645; --accent-blue: #2962ff;
                --border-color: #2a2e39;
            }}
            body {{ font-family: -apple-system, sans-serif; background: var(--bg-color); color: var(--text-main); padding: 40px 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; margin-bottom: 40px; color: #fff; letter-spacing: 2px; }}
            .card {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
            .card-header {{ padding: 20px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }}
            .symbol {{ font-size: 1.8em; font-weight: 700; color: #fff; margin-right: 10px; }}
            .name {{ color: var(--text-sub); font-size: 0.9em; }}
            .price {{ font-size: 1.5em; font-weight: 600; color: #fff; margin-right: 15px; }}
            .badge {{ background: rgba(242, 54, 69, 0.15); color: var(--accent-red); padding: 5px 10px; border-radius: 4px; font-weight: bold; }}
            .card-body {{ display: flex; flex-wrap: wrap; height: 450px; }}
            .news-section {{ flex: 1; min-width: 300px; padding: 20px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; }}
            .news-list {{ flex-grow: 1; overflow-y: auto; }}
            .news-item {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }}
            .news-item a {{ color: var(--text-main); text-decoration: none; }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            .date {{ font-size: 0.75em; color: var(--text-sub); margin-right: 5px; }}
            .no-news {{ color: var(--text-sub); font-style: italic; }}
            .news-footer {{ padding-top: 15px; border-top: 1px solid var(--border-color); text-align: center; }}
            .google-btn {{ background: #2a2e39; color: #fff; padding: 8px 16px; border-radius: 20px; text-decoration: none; font-size: 0.85em; transition: 0.3s; }}
            .google-btn:hover {{ background: var(--accent-blue); }}
            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            @media (max-width: 768px) {{ .card-body {{ height: auto; }} .news-section {{ border-right: none; border-bottom: 1px solid var(--border-color); }} .chart-section {{ height: 400px; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>TURNAROUND SNIPER <span style="font-size:0.5em; color:#777;">V6.1</span></h1>
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
        targets = [{"symbol": "MARA", "price": 10.22, "dd": -56.42, "name": "Marathon Digital"}]
    generate_dashboard(targets)
