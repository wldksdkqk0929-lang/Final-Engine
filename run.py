import sys
import subprocess
import os
import json
import logging
from datetime import datetime

# [핵심] yfinance가 없으면 파이썬이 스스로 설치하는 코드 (이게 에러를 막아줍니다)
try:
    import yfinance as yf
except ImportError:
    print("⚠️ yfinance module not found. Installing immediately...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
    import yfinance as yf

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        
        # 기본 정보
        info = ticker.info
        return {
            "name": info.get('shortName', symbol),
            "sector": info.get('sector', 'Unknown'),
            "industry": info.get('industry', 'Unknown'),
            "news": formatted_news,
            "current_price": info.get('currentPrice', 0),
            # 테스트용 가짜 데이터 (실제 데이터 연동 전 시각화 확인용)
            "dd_52w_pct": -45.2, 
            "rsi_14": 32.5
        }
    except Exception as e:
        logging.error(f"Error fetching data for {symbol}: {e}")
        return {"name": symbol, "sector": "-", "industry": "-", "news": []}

def generate_dashboard(survivors):
    """HTML 대시보드 생성"""
    html_head = """
    <html>
    <head>
        <title>Turnaround Sniper Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: 'Segoe UI', sans-serif; background-color: #f0f2f5; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; }
            .card { background: white; margin-bottom: 20px; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); display: flex; gap: 20px;}
            .info-panel { flex: 1; }
            .chart-panel { flex: 1; height: 350px; }
            .stock-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
            .symbol { font-size: 1.8em; font-weight: bold; color: #1a237e; }
            .metrics { display: flex; gap: 10px; margin-bottom: 15px; }
            .metric { background: #e8eaf6; padding: 8px 15px; border-radius: 5px; font-weight: bold; }
            .news-item { margin-bottom: 8px; border-bottom: 1px solid #eee; padding-bottom: 5px; }
            .news-item a { text-decoration: none; color: #2962ff; font-weight: 500; }
            .news-meta { font-size: 0.8em; color: #777; margin-left: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 style="text-align:center; color:#1a237e;">🎯 Turnaround Sniper Targets</h1>
    """

    html_body = ""
    for stock in survivors:
        # TradingView Widget
        chart_widget = f"""
        <div class="tradingview-widget-container" style="height:100%;width:100%">
          <div id="tradingview_{stock['symbol']}" style="height:100%;width:100%"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "autosize": true,
            "symbol": "{stock['symbol']}",
            "interval": "D",
            "timezone": "Etc/UTC",
            "theme": "light",
            "style": "1",
            "locale": "en",
            "enable_publishing": false,
            "hide_side_toolbar": false,
            "container_id": "tradingview_{stock['symbol']}"
          }});
          </script>
        </div>
        """

        news_html = ""
        for n in stock['news']:
            news_html += f"<div class='news-item'><a href='{n['link']}' target='_blank'>{n['title']}</a><span class='news-meta'>[{n['publisher']}]</span></div>"

        html_body += f"""
            <div class="card">
                <div class="info-panel">
                    <div class="stock-header">
                        <span class="symbol">{stock['symbol']}</span>
                        <span style="color:#666;">{stock['name']}</span>
                    </div>
                    <div class="metrics">
                        <div class="metric">Price: ${stock.get('current_price', 0)}</div>
                        <div class="metric" style="color:red">Drawdown: {stock.get('dd_52w_pct', 0)}%</div>
                    </div>
                    <h4>📰 Latest News</h4>
                    {news_html if news_html else "<p>No recent news.</p>"}
                </div>
                <div class="chart-panel">
                    {chart_widget}
                </div>
            </div>
        """

    html_footer = "</div></body></html>"

    # 저장
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(html_head + html_body + html_footer)
    print("✅ Dashboard generated successfully!")

def main():
    print("🚀 Starting Engine (Self-Healing Mode)")
    
    # 테스트용 종목 리스트 (실제 로직 연결 전 시각화 우선 확인)
    # 기존 모듈 로드 실패를 대비해 하드코딩된 리스트로 우선 실행 보장
    target_tickers = ["INTC", "WBA", "PFE", "NKE", "TSLA"]
    
    final_data = []
    for ticker in target_tickers:
        print(f"Processing {ticker}...")
        data = get_news_and_info(ticker)
        data['symbol'] = ticker
        final_data.append(data)
    
    generate_dashboard(final_data)
    print("🏁 All Done.")

if __name__ == "__main__":
    main()
