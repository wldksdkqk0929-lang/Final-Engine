import os
import json
import yaml
import logging
import yfinance as yf
from datetime import datetime

# 사용자님의 기존 프로젝트 구조에 맞는 라이브러리 임포트
# (만약 src 모듈 경로가 다르다면 기존 run.py의 임포트 부분을 유지하세요)
try:
    from src.universe import UniverseLoader
    from src.scanner import UniverseScanner
    from src.filter import CandidateFilter
except ImportError:
    # 비상용: 모듈을 못 찾을 경우를 대비한 더미 클래스 (실제 환경에선 기존 모듈이 작동함)
    print("⚠️ Warning: src module not found. Running in standalone mode for testing.")
    class UniverseLoader:
        def __init__(self, config): pass
        def load(self): return []
    class UniverseScanner:
        def __init__(self, config): pass
        def scan(self, universe): return []
    class CandidateFilter:
        def __init__(self, config): pass
        def filter(self, candidates): return []

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def load_config(path="config/base.yaml"):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def get_news_and_info(symbol):
    """yfinance를 이용해 뉴스 헤드라인과 기본 정보 수집"""
    try:
        ticker = yf.Ticker(symbol)
        # 뉴스 가져오기 (최신 3개)
        news = ticker.news[:3] if ticker.news else []
        formatted_news = []
        for n in news:
            formatted_news.append({
                "title": n.get('title', 'No Title'),
                "link": n.get('link', '#'),
                "publisher": n.get('publisher', 'Unknown'),
                "published": datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%Y-%m-%d')
            })
        
        # 기본 정보 (이름, 섹터 등)
        info = ticker.info
        return {
            "name": info.get('shortName', symbol),
            "sector": info.get('sector', 'Unknown'),
            "industry": info.get('industry', 'Unknown'),
            "news": formatted_news
        }
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return {"name": symbol, "sector": "-", "industry": "-", "news": []}

def generate_dashboard(survivors):
    """HTML 대시보드 생성 (TradingView 차트 포함)"""
    html_head = """
    <html>
    <head>
        <title>Turnaround Sniper Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .header { background: #1a237e; color: white; padding: 20px; border-radius: 10px 10px 0 0; text-align: center; }
            .card { background: white; margin-bottom: 20px; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; flex-wrap: wrap; }
            .info-panel { flex: 1; min-width: 300px; padding-right: 20px; }
            .chart-panel { flex: 1; min-width: 400px; height: 300px; }
            .stock-title { font-size: 1.5em; font-weight: bold; color: #333; }
            .stock-meta { color: #666; font-size: 0.9em; margin-bottom: 15px; }
            .metrics { display: flex; gap: 15px; margin-bottom: 15px; }
            .metric-box { background: #e8eaf6; padding: 10px; border-radius: 5px; text-align: center; flex: 1; }
            .metric-val { font-weight: bold; color: #1a237e; font-size: 1.1em; }
            .metric-label { font-size: 0.8em; color: #555; }
            .news-list { list-style: none; padding: 0; }
            .news-item { margin-bottom: 8px; font-size: 0.9em; border-bottom: 1px solid #eee; padding-bottom: 5px; }
            .news-item a { text-decoration: none; color: #2962ff; }
            .news-item a:hover { text-decoration: underline; }
            .news-date { font-size: 0.8em; color: #999; margin-left: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Turnaround Sniper Targets</h1>
                <p>Top Oversold Survivors & Market Intel</p>
            </div>
    """

    html_body = ""
    for stock in survivors:
        # TradingView Widget Script (무료, API 키 불필요)
        chart_widget = f"""
        <div class="tradingview-widget-container">
          <div id="tradingview_{stock['symbol']}"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget(
          {{
            "width": "100%",
            "height": 300,
            "symbol": "{stock['symbol']}",
            "interval": "D",
            "timezone": "Etc/UTC",
            "theme": "light",
            "style": "1",
            "locale": "en",
            "toolbar_bg": "#f1f3f6",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "allow_symbol_change": true,
            "container_id": "tradingview_{stock['symbol']}"
          }}
          );
          </script>
        </div>
        """

        news_html = ""
        for n in stock['news']:
            news_html += f"<li class='news-item'><a href='{n['link']}' target='_blank'>{n['title']}</a><span class='news-date'>[{n['published']}]</span></li>"
        
        html_body += f"""
            <div class="card">
                <div class="info-panel">
                    <div class="stock-title">{stock['symbol']} <span style="font-size:0.6em; font-weight:normal; color:#777;">{stock.get('name', '')}</span></div>
                    <div class="stock-meta">{stock.get('sector', '')} | {stock.get('industry', '')}</div>
                    
                    <div class="metrics">
                        <div class="metric-box">
                            <div class="metric-val">{stock.get('current_price', 'N/A')}</div>
                            <div class="metric-label">Price</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-val" style="color:red;">{stock.get('dd_52w_pct', 0):.1f}%</div>
                            <div class="metric-label">52W Drawdown</div>
                        </div>
                        <div class="metric-box">
                            <div class="metric-val">{stock.get('rsi_14', 'N/A')}</div>
                            <div class="metric-label">RSI (14)</div>
                        </div>
                    </div>
                    
                    <h4>📰 Recent Intel</h4>
                    <ul class="news-list">
                        {news_html if news_html else "<li>No recent news found.</li>"}
                    </ul>
                </div>
                <div class="chart-panel">
                    {chart_widget}
                </div>
            </div>
        """

    html_footer = """
        </div>
    </body>
    </html>
    """
    
    # HTML 파일 저장
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(html_head + html_body + html_footer)
    logging.info("✅ Dashboard generated at data/artifacts/dashboard/index.html")


def main():
    logging.info("🚀 Starting Turnaround Sniper Engine (Visualization Mode)")
    
    # 1. 설정 로드
    config = load_config()
    
    # 2. 유니버스 로드 (기존 로직 사용)
    # (여기서는 예외 처리를 통해 기존 코드가 작동하도록 함)
    try:
        loader = UniverseLoader(config)
        universe = loader.load()
        logging.info(f"🌌 Universe loaded: {len(universe)} symbols")
        
        # 3. 스캐너 가동 (기존 로직 사용 - 52주 낙폭 등)
        scanner = UniverseScanner(config)
        candidates_raw = scanner.scan(universe)
        logging.info(f"🔍 Scanned candidates: {len(candidates_raw)}")
        
        # 4. 필터링 (기존 로직 사용 - 우량주 선별)
        filter_engine = CandidateFilter(config)
        survivors = filter_engine.filter(candidates_raw) # 여기서 Top 30이 나옴
        logging.info(f"⚔️ Final Survivors: {len(survivors)}")
        
    except NameError:
        # 혹시 모듈 로드 실패 시, 테스트를 위해 방금 성공한 로그의 데이터를 수동 로드
        logging.warning("⚠️ Module load failed or test mode. Attempting to load last known survivors.")
        # (실제 환경에선 이 부분은 실행 안 됨)
        survivors = [] 
        # 안전장치: 파일이 있으면 불러오기
        if os.path.exists("data/processed/survivors/survivors.json"):
             with open("data/processed/survivors/survivors.json", 'r') as f:
                 survivors = json.load(f)

    # 5. [핵심 변경] AI 분석 대신 -> 정보 보강 및 시각화
    final_data = []
    for stock in survivors:
        # yfinance로 뉴스/기본정보 추가 보강
        intel = get_news_and_info(stock['symbol'])
        
        # 기존 데이터와 병합
        merged_data = {**stock, **intel}
        final_data.append(merged_data)
        logging.info(f"✨ Enriched data for {stock['symbol']}")

    # 6. 대시보드 생성 (그래프 포함)
    generate_dashboard(final_data)
    logging.info("🏁 Engine run complete.")

if __name__ == "__main__":
    main()
