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
yaml = install_and_import("yaml")

# ==========================================
# 2. 로직: 낙폭 과대주 선별 (Brain)
# ==========================================
def run_logic():
    print("🧠 [Brain] 낙폭 과대주 분석 엔진 가동...")
    
    # 분석 대상 유니버스 (변동성 큰 기술/성장주 위주)
    universe = ["MARA", "LCID", "TSLA", "INTC", "PLTR", "SOFI", "AMD", "NVDA", "RIVN", "OPEN", "IONQ", "JOBY"]
    
    survivors = []
    print(f"🔍 {len(universe)}개 종목 스캔 중...")
    
    for sym in universe:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 20: continue
            
            high = hist['High'].max()
            cur = hist['Close'].iloc[-1]
            
            # 낙폭 계산
            dd = ((cur - high) / high) * 100
            
            # [조건] 고점 대비 -40% 이상 하락한 종목만 통과
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
# 3. 시각화: 다크 모드 & 뉴스 기능 강화
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        # --- [뉴스 데이터 처리 강화] ---
        news_html = ""
        try:
            t = yf.Ticker(sym)
            raw_news = t.news
            
            if raw_news:
                count = 0
                for n in raw_news:
                    if count >= 3: break # 최대 3개
                    
                    # 제목 추출 시도 (여러 키 확인)
                    title = n.get('title', n.get('headline', ''))
                    link = n.get('link', f"https://finance.yahoo.com/quote/{sym}")
                    
                    # 날짜 변환
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
            
            # 뉴스가 없거나 제목 추출 실패 시
            if not news_html: 
                news_html = "<p class='no-news'>야후 파이낸스 데이터 수신 대기중...</p>"

        except Exception as e:
            news_html = f"<p class='no-news'>뉴스 로딩 실패 ({str(e)})</p>"

        # [필살기] 구글 뉴스 검색 버튼 추가
        google_search_url = f"https://www.google.com/search?q={sym}+stock+news&tbm=nws"
        news_footer = f"""
        <div class="news-footer">
            <a href="{google_search_url}" target="_blank" class="google-btn">
                🔍 Google News 실시간 검색
            </a>
        </div>
        """

        # --- [카드 HTML 조립] ---
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
                            "autosize": true,
                            "symbol": "{sym}",
                            "interval": "D",
                            "timezone": "Etc/UTC",
                            "theme": "dark",
                            "style": "1",
                            "locale": "kr",
                            "toolbar_bg": "#1e222d",
                            "enable_publishing": false,
                            "hide_side_toolbar": false,
                            "allow_symbol_change": true,
                            "container_id": "{chart_id}"
                        }});
                        </script>
                    </div>
                </div>
            </div>
        </div>
        """

    # --- [전체 HTML 조립 (CSS 유지)] ---
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sniper Dark Terminal</title>
        <style>
            :root {{
                --bg-color: #131722;
                --card-bg: #1e222d;
                --text-main: #d1d4dc;
                --text-sub: #787b86;
                --accent-red: #f23645;
                --accent-blue: #2962ff;
                --border-color: #2a2e39;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-main);
                margin: 0;
                padding: 40px 20px;
            }}
            
            .container {{ max-width: 1200px; margin: 0 auto; }}
            
            h1 {{
                text-align: center;
                font-weight: 800;
                margin-bottom: 40px;
                letter-spacing: 1px;
                text-transform: uppercase;
                background: linear-gradient(to right, #2962ff, #f23645);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }}

            .card {{
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                margin-bottom: 30px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }}
            
            .card-header {{
                padding: 20px 25px;
                border-bottom: 1px solid var(--border-color);
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            
            .symbol {{ font-size: 1.8em; font-weight: 700; color: #fff; margin-right: 10px; }}
            .name {{ color: var(--text-sub); font-size: 0.9em; }}
            .price {{ font-size: 1.5em; font-weight: 600; margin-right: 15px; color: #fff; }}
            .badge {{ 
                background-color: rgba(242, 54, 69, 0.15); 
                color: var(--accent-red); 
                padding: 6px 12px; 
                border-radius: 4px; 
                font-weight: bold; 
            }}
            
            .card-body {{ display: flex; flex-wrap: wrap; height: 450px; }}
            
            .news-section {{
                flex: 1;
                min-width: 300px;
                padding: 20px 25px;
                border-right: 1px solid var(--border-color);
                background-color: #1e222d;
                display: flex;
                flex-direction: column;
            }}
            
            .news-section h4 {{
                color: var(--text-sub);
                font-size: 0.8em;
                margin-top: 0;
                margin-bottom: 20px;
                letter-spacing: 1px;
            }}
            
            .news-list {{ flex-grow: 1; overflow-y: auto; }}
            
            .news-item {{ margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid var(--border-color); }}
            .news-item:last-child {{ border-bottom: none; }}
            
            .news-item a {{
                color: var(--text-main);
                text-decoration: none;
                font-size: 0.95em;
                display: block;
                margin-bottom: 5px;
                transition: color 0.2s;
            }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            
            .date {{ font-size: 0.75em; color: var(--text-sub); }}
            .no-news {{ color: var(--text-sub); font-style: italic; font-size: 0.9em; }}

            /* 구글 검색 버튼 스타일 */
            .news-footer {{ margin-top: auto; padding-top: 15px; border-top: 1px solid var(--border-color); text-align: center; }}
            .google-btn {{
                display: inline-block;
                background-color: #2a2e39;
                color: #fff;
                text-decoration: none;
                padding: 8px 16px;
                border-radius: 20px;
                font-size: 0.85em;
                transition: background 0.3s;
            }}
            .google-btn:hover {{ background-color: #2962ff; }}

            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            
            @media (max-width: 768px) {{
                .card-body {{ height: auto; flex-direction: column; }}
                .news-section {{ border-right: none; border-bottom: 1px solid var(--border-color); max-height: 350px; }}
                .chart-section {{ height: 400px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Turnaround Sniper <span style="font-size:0.5em; color:#555; vertical-align:middle">V6 TERMINAL</span></h1>
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
        # 혹시 종목이 없으면 테스트용으로 MARA 추가
        targets = [{"symbol": "MARA", "price": 10.22, "dd": -56.42, "name": "Marathon Digital"}]
    generate_dashboard(targets)
