import sys
import subprocess
import os
from datetime import datetime

# ==========================================
# 🚨 [핵심] yfinance 강제 설치 코드 (yml 무시)
# ==========================================
try:
    import yfinance as yf
except ImportError:
    print("⚠️ yfinance 모듈이 없네요? 지금 바로 강제 설치합니다...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
        import yfinance as yf
        print("✅ yfinance 설치 완료! 실행을 계속합니다.")
    except Exception as e:
        print(f"❌ 설치 실패: {e}")
        sys.exit(1)

# ==========================================
# 🚀 여기서부터 대시보드 생성 로직
# ==========================================
def main():
    print("🚀 Turnaround Sniper 대시보드 생성 시작")
    
    # 목표 종목 리스트 (우량 낙폭 과대주)
    targets = ["TSLA", "INTC", "PFE", "NKE", "AAPL", "AMD", "NVDA", "PLTR", "SOFI", "MARA"]
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>TS-Project Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f0f2f5; padding: 20px; }
            .container { max-width: 1000px; margin: 0 auto; }
            .header { text-align: center; margin-bottom: 30px; color: #1a237e; }
            .card { background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 24px; overflow: hidden; }
            .card-header { background: #f8f9fa; padding: 15px 20px; border-bottom: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; }
            .symbol { font-size: 1.4em; font-weight: 800; color: #333; }
            .badge { background: #ffebee; color: #c62828; padding: 4px 8px; border-radius: 4px; font-size: 0.85em; font-weight: bold; }
            .content { display: flex; flex-wrap: wrap; }
            .news-section { flex: 1; min-width: 300px; padding: 20px; border-right: 1px solid #eee; }
            .chart-section { flex: 1.5; min-width: 400px; height: 400px; }
            .news-item { margin-bottom: 12px; font-size: 0.95em; line-height: 1.4; }
            .news-item a { text-decoration: none; color: #0066cc; font-weight: 500; }
            .news-item a:hover { text-decoration: underline; }
            .news-date { font-size: 0.8em; color: #888; margin-left: 6px; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🎯 Sniper Dashboard</h1>
                <p>실시간 뉴스 & 차트 브리핑</p>
            </div>
    """

    for symbol in targets:
        print(f"Processing {symbol}...")
        try:
            # 뉴스 데이터 수집
            ticker = yf.Ticker(symbol)
            news = ticker.news[:3] if ticker.news else []
            
            news_html = ""
            for n in news:
                title = n.get('title', '뉴스 제목 없음')
                link = n.get('link', '#')
                pub_time = datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%Y-%m-%d')
                news_html += f"""
                <div class="news-item">
                    <a href="{link}" target="_blank">📄 {title}</a>
                    <span class="news-date">{pub_time}</span>
                </div>
                """
            
            if not news_html:
                news_html = "<p style='color:#999'>최근 뉴스가 없습니다.</p>"

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
            <div class="card">
                <div class="card-header">
                    <span class="symbol">{symbol}</span>
                    <span class="badge">Target</span>
                </div>
                <div class="content">
                    <div class="news-section">
                        <h4 style="margin-top:0; color:#555;">📰 최신 뉴스</h4>
                        {news_html}
                    </div>
                    <div class="chart-section">
                        {chart_widget}
                    </div>
                </div>
            </div>
            """
            
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    html_content += "</div></body></html>"
    
    # 결과 저장
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print("✅ 대시보드 생성 완료: data/artifacts/dashboard/index.html")

if __name__ == "__main__":
    main()
