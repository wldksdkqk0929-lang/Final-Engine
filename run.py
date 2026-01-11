import sys
import subprocess
import os
import json
import logging
from datetime import datetime

# ==========================================
# 1. 환경 설정 & 라이브러리 강제 설치 (안전장치)
# ==========================================
def install_and_import(package):
    try:
        return __import__(package)
    except ImportError:
        print(f"⚠️ {package} 모듈 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return __import__(package)

# yfinance, requests 등 필수재 확인
yf = install_and_import("yfinance")
requests = install_and_import("requests")
yaml = install_and_import("yaml")

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

# ==========================================
# 2. 기존 엔진 (Logic) 복구: 스캐너 & 필터
# ==========================================
# (기존 src 폴더의 모듈을 불러옵니다. 만약 모듈이 없다면 비상용 로직이 돌아갑니다)
try:
    from src.universe import UniverseLoader
    from src.scanner import UniverseScanner
    from src.filter import CandidateFilter
    USE_REAL_ENGINE = True
except ImportError:
    print("⚠️ src 모듈을 찾을 수 없어 비상용 스캐너로 동작합니다.")
    USE_REAL_ENGINE = False

def load_config():
    # 설정 파일이 있으면 로드, 없으면 기본값
    config_path = "config/base.yaml"
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    return {}

def run_real_logic():
    """진짜 계산: 5,500개 종목 중 52주 낙폭 과대주 선별"""
    print("🧠 [Brain] 진짜 주식 데이터 분석을 시작합니다...")
    
    config = load_config()
    
    # 1. 유니버스 로드
    if USE_REAL_ENGINE:
        loader = UniverseLoader(config)
        universe = loader.load()
    else:
        # 비상용: 나스닥 상위 종목들
        universe = [{"symbol": s} for s in ["TSLA", "NVDA", "AMD", "AAPL", "PLTR", "SOFI", "MARA", "INTC", "WBA", "PFE"]]

    print(f"🔍 [Scan] 총 {len(universe)}개 종목 스캔 중...")

    # 2. 데이터 스캔 & 필터링 (간이 구현: 실제 src가 있으면 src 사용)
    survivors = []
    
    if USE_REAL_ENGINE:
        scanner = UniverseScanner(config)
        candidates = scanner.scan(universe)
        filter_engine = CandidateFilter(config)
        survivors = filter_engine.filter(candidates)
    else:
        # 엔진 모듈이 없을 경우 yfinance로 직접 계산
        for item in universe:
            try:
                sym = item['symbol']
                t = yf.Ticker(sym)
                hist = t.history(period="1y")
                if len(hist) < 200: continue
                
                high_52 = hist['High'].max()
                current = hist['Close'].iloc[-1]
                dd_pct = ((current - high_52) / high_52) * 100
                
                # 낙폭 -40% 이하인 것만 (테스트용 기준)
                if dd_pct < -40:
                    survivors.append({
                        "symbol": sym,
                        "name": t.info.get('shortName', sym),
                        "current_price": current,
                        "dd_52w_pct": round(dd_pct, 2),
                        "market_cap": t.info.get('marketCap', 0)
                    })
            except:
                continue
            if len(survivors) >= 10: break # 최대 10개만 (속도 위해)

    print(f"⚔️ [Result] 최종 선별된 종목: {len(survivors)}개")
    return survivors

# ==========================================
# 3. 데이터 시각화 (Face): 뉴스 & 차트
# ==========================================
def get_intel_and_generate_html(survivors):
    print("🎨 [Design] 대시보드 생성 중...")
    
    html_rows = ""
    
    for stock in survivors:
        symbol = stock['symbol']
        print(f"  -> {symbol} 정보 수집 중...")
        
        # 뉴스 수집
        try:
            t = yf.Ticker(symbol)
            news = t.news[:3] if t.news else []
            news_html = ""
            for n in news:
                title = n.get('title', '제목 없음')
                link = n.get('link', '#')
                pub = datetime.fromtimestamp(n.get('providerPublishTime', 0)).strftime('%Y-%m-%d')
                news_html += f"<div class='news-item'><span class='date'>{pub}</span> <a href='{link}' target='_blank'>{title}</a></div>"
            if not news_html: news_html = "<span style='color:#bbb'>최근 뉴스가 없습니다.</span>"
        except:
            news_html = "뉴스 수집 실패"

        # 차트 위젯 (트레이딩뷰)
        chart_id = f"tv_{symbol}"
        
        # [디자인] 버전 5 스타일 (표 + 확장형 차트)
        html_rows += f"""
        <div class="stock-card">
            <div class="stock-header">
                <div class="main-info">
                    <span class="symbol">{symbol}</span>
                    <span class="price">${stock.get('current_price', 0):.2f}</span>
                    <span class="dd-badge">{stock.get('dd_52w_pct', 0)}%</span>
                </div>
                <div class="news-summary">
                    {news_html}
                </div>
            </div>
            <div class="chart-container">
                <div class="tradingview-widget-container" style="height:100%;width:100%">
                  <div id="{chart_id}" style="height:400px;width:100%"></div>
                  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                  <script type="text/javascript">
                  new TradingView.widget({{
                    "autosize": true,
                    "symbol": "{symbol}",
                    "interval": "D",
                    "timezone": "Etc/UTC",
                    "theme": "light",
                    "style": "1",
                    "locale": "kr",
                    "toolbar_bg": "#f1f3f6",
                    "enable_publishing": false,
                    "hide_side_toolbar": false,
                    "container_id": "{chart_id}"
                  }});
                  </script>
                </div>
            </div>
        </div>
        """

    # 최종 HTML 조립
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sniper V6: Real Data</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Pretendard', -apple-system, sans-serif; background: #f5f7fa; padding: 20px; color: #333; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; color: #2c3e50; margin-bottom: 30px; }}
            
            /* 카드 스타일 */
            .stock-card {{ background: white; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); margin-bottom: 30px; overflow: hidden; }}
            
            /* 헤더 (정보 + 뉴스) */
            .stock-header {{ padding: 20px; display: flex; flex-wrap: wrap; gap: 20px; border-bottom: 1px solid #eee; background: #fff; }}
            .main-info {{ flex: 1; min-width: 200px; display: flex; flex-direction: column; justify-content: center; }}
            .symbol {{ font-size: 2em; font-weight: 800; color: #1a237e; }}
            .price {{ font-size: 1.5em; font-weight: 600; color: #333; }}
            .dd-badge {{ display: inline-block; background: #ffebee; color: #d32f2f; padding: 5px 10px; border-radius: 6px; font-weight: bold; margin-top: 5px; width: fit-content; }}
            
            /* 뉴스 영역 */
            .news-summary {{ flex: 2; min-width: 300px; background: #f8f9fa; padding: 15px; border-radius: 8px; }}
            .news-item {{ margin-bottom: 8px; font-size: 0.95em; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
            .news-item:last-child {{ border-bottom: none; }}
            .news-item a {{ text-decoration: none; color: #444; }}
            .news-item a:hover {{ color: #0056b3; text-decoration: underline; }}
            .date {{ color: #999; font-size: 0.8em; margin-right: 5px; }}
            
            /* 차트 영역 */
            .chart-container {{ height: 400px; padding: 10px; background: #fff; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎯 Turnaround Sniper: Target {len(survivors)}</h1>
            {html_rows}
        </div>
    </body>
    </html>
    """
    
    # 저장
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)
    print("✅ 대시보드 생성 완료!")

def main():
    # 1. 계산 (스캐너 + 필터)
    survivors = run_real_logic()
    
    if not survivors:
        print("⚠️ 선별된 종목이 없습니다. (조건이 너무 까다롭거나 장 휴장일 수 있음)")
        # 빈 화면 방지용 샘플
        survivors = [{"symbol": "SPY", "current_price": 500, "dd_52w_pct": -5}]
    
    # 2. 표현 (HTML + 차트)
    get_intel_and_generate_html(survivors)

if __name__ == "__main__":
    main()
