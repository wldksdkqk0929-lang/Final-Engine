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
    
    # 분석 대상 유니버스 (대표적인 변동성 종목들)
    universe = ["MARA", "TSLA", "INTC", "PLTR", "SOFI", "AMD", "NVDA", "WBA", "PFE", "GOOGL", "RIVN", "LCID"]
    
    survivors = []
    print(f"🔍 {len(universe)}개 종목 스캔 중...")
    
    for sym in universe:
        try:
            t = yf.Ticker(sym)
            # 1년치 데이터 가져오기
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
# 3. 시각화: 다크 모드 대시보드 (Dark UI)
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        # 뉴스 데이터 수집 (날짜 버그 수정 포함)
        try:
            t = yf.Ticker(sym)
            raw_news = t.news
            news_html = ""
            if raw_news:
                for n in raw_news[:3]: # 최신 3개
                    title = n.get('title', n.get('headline', '제목 없음'))
                    link = n.get('link', '#')
                    
                    # 날짜 변환 (1970년 버그 수정)
                    ts = n.get('providerPublishTime', 0)
                    if ts > 0:
                        date_str = datetime.fromtimestamp(ts).strftime('%Y.%m.%d')
                    else:
                        date_str = ""
                    
                    if title:
                        news_html += f"""
                        <div class='news-item'>
                            <span class='date'>{date_str}</span>
                            <a href='{link}' target='_blank'>{title}</a>
                        </div>
                        """
            
            if not news_html: 
                news_html = "<p class='no-news'>최근 뉴스 데이터가 없습니다.</p>"
                
        except Exception as e:
            news_html = f"<p class='error'>뉴스 로딩 실패</p>"

        # 카드 HTML 조립
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
                    {news_html}
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
                            "theme": "dark",  /* 여기가 핵심: 다크 모드 */
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

    # 전체 HTML 조립 (CSS: 다크 테마 적용)
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sniper Dark Terminal</title>
        <style>
            /* 다크 모드 기본 설정 */
            :root {{
                --bg-color: #131722;       /* 트레이딩뷰 기본 배경색 */
                --card-bg: #1e222d;        /* 카드 배경색 */
                --text-main: #d1d4dc;      /* 기본 텍스트 */
                --text-sub: #787b86;       /* 보조 텍스트 */
                --accent-red: #f23645;     /* 하락/강조 색상 */
                --accent-blue: #2962ff;    /* 링크 색상 */
                --border-color: #2a2e39;   /* 테두리 색상 */
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Helvetica Neue", sans-serif;
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

            /* 카드 스타일 */
            .card {{
                background-color: var(--card-bg);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                margin-bottom: 30px;
                overflow: hidden;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }}
            
            /* 카드 헤더 */
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
                font-size: 1em;
            }}
            
            /* 카드 바디 */
            .card-body {{ display: flex; flex-wrap: wrap; height: 450px; }}
            
            /* 뉴스 영역 */
            .news-section {{
                flex: 1;
                min-width: 300px;
                padding: 20px 25px;
                border-right: 1px solid var(--border-color);
                overflow-y: auto;
                background-color: #1e222d;
            }}
            
            .news-section h4 {{
                color: var(--text-sub);
                font-size: 0.8em;
                margin-top: 0;
                margin-bottom: 20px;
                letter-spacing: 1px;
            }}
            
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

            /* 차트 영역 */
            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            
            /* 모바일 대응 */
            @media (max-width: 768px) {{
                .card-body {{ height: auto; flex-direction: column; }}
                .news-section {{ border-right: none; border-bottom: 1px solid var(--border-color); max-height: 300px; }}
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
        # 조건에 맞는게 없으면 MARA 강제 추가 (화면 확인용)
        targets = [{"symbol": "MARA", "price": 10.22, "dd": -56.42, "name": "Marathon Digital"}]
    generate_dashboard(targets)
