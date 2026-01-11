import sys
import subprocess
import os
import logging
import xml.etree.ElementTree as ET # RSS 파싱용 (기본 내장)
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
requests = install_and_import("requests")
yaml = install_and_import("yaml")

# ==========================================
# 2. 로직: 낙폭 과대주 선별 (Brain) - 성공 ✅
# ==========================================
def run_logic():
    print("🧠 [Brain] 낙폭 과대주 분석 엔진 가동...")
    
    # 100% 리얼 엔진 가동 (테스트용 하드코딩 아님)
    # 우량 기술주 및 변동성 상위 종목 유니버스
    universe = [
        "MARA", "LCID", "TSLA", "INTC", "PLTR", "SOFI", "AMD", "NVDA", 
        "RIVN", "OPEN", "IONQ", "JOBY", "UPST", "AFRM", "COIN", "MSTR"
    ]
    
    survivors = []
    print(f"🔍 {len(universe)}개 종목 정밀 스캔 중...")
    
    for sym in universe:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            
            # 데이터가 너무 적으면 패스
            if len(hist) < 20: continue
            
            high = hist['High'].max()
            cur = hist['Close'].iloc[-1]
            
            # 낙폭 계산
            dd = ((cur - high) / high) * 100
            
            # [조건] 고점 대비 -40% 이상 하락한 종목만 통과
            if dd < -40:
                print(f"  -> 🎯 타겟 포착: {sym} ({dd:.2f}%)")
                survivors.append({
                    "symbol": sym,
                    "price": cur,
                    "dd": round(dd, 2),
                    "name": t.info.get('shortName', sym)
                })
        except:
            continue
            
    # 낙폭이 큰 순서대로 정렬
    survivors.sort(key=lambda x: x['dd'])
    
    print(f"⚔️ 최종 생존 종목: {len(survivors)}개")
    return survivors

# ==========================================
# 3. 뉴스 엔진: 구글 뉴스 RSS (NEW 🚀)
# ==========================================
def get_google_news_rss(symbol):
    """
    야후 파이낸스 대신 차단 걱정 없는 '구글 뉴스 RSS'를 사용합니다.
    """
    try:
        # 구글 뉴스 RSS URL (종목 검색)
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        
        # 깃허브 서버에서도 잘 통하는 일반 요청
        resp = requests.get(url, timeout=5)
        
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            news_items = []
            
            # 상위 3개 뉴스 추출
            for item in root.findall('./channel/item')[:3]:
                title = item.find('title').text
                link = item.find('link').text
                pubDate = item.find('pubDate').text
                
                # 날짜 포맷 정리 (Mon, 12 Jan 2026 -> 2026.01.12)
                try:
                    dt = datetime.strptime(pubDate[:16], "%a, %d %b %Y")
                    date_str = dt.strftime("%Y.%m.%d")
                except:
                    date_str = "" # 날짜 변환 실패시 공란

                # 출처(Source)가 제목에 포함된 경우 깔끔하게 정리
                # 예: "Stock jumps 10% - CNBC" -> "Stock jumps 10%"
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0]

                news_items.append({
                    "title": title,
                    "link": link,
                    "date": date_str
                })
            return news_items
            
    except Exception as e:
        print(f"⚠️ {symbol} 구글 뉴스 가져오기 실패: {e}")
        return []
    
    return []

# ==========================================
# 4. 시각화: 대시보드 생성 (V6.1 Terminal)
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        # --- [뉴스 데이터 수집: 구글 RSS] ---
        news_data = get_google_news_rss(sym)
        
        news_html = ""
        if news_data:
            for n in news_data:
                news_html += f"""
                <div class='news-item'>
                    <span class='date'>{n['date']}</span>
                    <a href='{n['link']}' target='_blank'>{n['title']}</a>
                </div>
                """
        else:
            news_html = "<p class='no-news'>최신 관련 뉴스가 없습니다.</p>"

        # 구글 뉴스 더보기 버튼
        google_search_url = f"https://www.google.com/search?q={sym}+stock+news&tbm=nws"
        news_footer = f"""
        <div class="news-footer">
            <a href="{google_search_url}" target="_blank" class="google-btn">
                More News on Google ➜
            </a>
        </div>
        """

        # --- [HTML 조립 (디자인 유지)] ---
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
                    <h4>NEWS BRIEFING (Google RSS)</h4>
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
            .news-section {{ flex: 1; min-width: 300px; padding: 20px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; background: #1e222d; }}
            .news-list {{ flex-grow: 1; overflow-y: auto; }}
            .news-item {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }}
            .news-item:last-child {{ border-bottom: none; }}
            .news-item a {{ color: var(--text-main); text-decoration: none; font-size: 0.95em; display: block; margin-top: 4px; }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            .date {{ font-size: 0.75em; color: var(--text-sub); display: block; }}
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
            <h1>TURNAROUND SNIPER <span style="font-size:0.5em; color:#777;">V6.2</span></h1>
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
    # 종목이 없을 경우를 대비한 안전장치 (화면 확인용)
    if not targets:
        print("⚠️ 스캔된 종목이 없습니다. (장이 좋거나 조건이 너무 까다로움)")
        targets = [{"symbol": "MARA", "price": 0.00, "dd": 0.00, "name": "No Targets Found"}]
    generate_dashboard(targets)
