import os
import yfinance as yf  # 1단계 설정을 하면 여기서 에러 안 남
from datetime import datetime

def main():
    print("🚀 엔진 시작: 뉴스 및 차트 데이터 수집 중...")
    
    # 1. 우량주 30개 (예시 리스트, 실제로는 이전 단계 데이터 사용 가능)
    targets = ["TSLA", "AAPL", "NVDA", "AMD", "INTC", "PLTR", "SOFI", "MARA", "GOOGL", "AMZN"]
    
    html_content = """
    <html>
    <head>
        <title>TS-Project Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: sans-serif; padding: 20px; background: #f4f4f9; }
            .card { background: white; margin-bottom: 20px; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            .flex { display: flex; gap: 20px; flex-wrap: wrap; }
            .info { flex: 1; min-width: 300px; }
            .chart { flex: 2; min-width: 400px; height: 400px; }
            h2 { margin-top: 0; color: #333; }
            a { text-decoration: none; color: #007bff; display: block; margin-bottom: 5px; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>🎯 Turnaround Sniper: 실시간 상황판</h1>
    """

    for symbol in targets:
        print(f"Processing {symbol}...")
        try:
            # 뉴스 가져오기
            ticker = yf.Ticker(symbol)
            news_list = ticker.news[:3] if ticker.news else []
            
            news_html = ""
            for n in news_list:
                title = n.get('title', 'No Title')
                link = n.get('link', '#')
                news_html += f"<a href='{link}' target='_blank'>📰 {title}</a>"

            # 트레이딩뷰 차트 위젯
            chart_widget = f"""
            <div class="tradingview-widget-container" style="height:100%;width:100%">
              <div id="tradingview_{symbol}" style="height:100%;width:100%"></div>
              <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
              <script type="text/javascript">
              new TradingView.widget({{
                "autosize": true,
                "symbol": "{symbol}",
                "interval": "D",
                "timezone": "Etc/UTC",
                "theme": "light",
                "style": "1",
                "locale": "en",
                "enable_publishing": false,
                "hide_side_toolbar": false,
                "container_id": "tradingview_{symbol}"
              }});
              </script>
            </div>
            """
            
            html_content += f"""
            <div class="card flex">
                <div class="info">
                    <h2>{symbol}</h2>
                    <p>최신 주요 뉴스:</p>
                    {news_html if news_html else "<p>뉴스 없음</p>"}
                </div>
                <div class="chart">
                    {chart_widget}
                </div>
            </div>
            """
        except Exception as e:
            print(f"Error {symbol}: {e}")

    html_content += "</body></html>"
    
    # 저장
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print("✅ 대시보드 생성 완료!")

if __name__ == "__main__":
    main()
