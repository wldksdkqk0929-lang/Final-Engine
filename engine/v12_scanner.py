import yfinance as yf
import json
import os
import datetime
import pandas as pd

# [설정]
WATCHLIST = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AMD", "PLTR"]
VIX_THRESHOLD = 35.0
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(BASE_DIR, 'market_status.json')
REPORT_FILE = os.path.join(BASE_DIR, 'final_v12_report.json')

def get_kst_time():
    utc_now = datetime.datetime.utcnow()
    kst_now = utc_now + datetime.timedelta(hours=9)
    return kst_now.strftime("%Y-%m-%d %H:%M:%S")

def analyze_technical(df, ticker):
    # 데이터 추출
    current_price = df['Close'].iloc[-1]
    open_price = df['Open'].iloc[-1]
    low_20d = df['Low'].min()
    high_20d = df['High'].max()
    avg_vol = df['Volume'].mean()
    curr_vol = df['Volume'].iloc[-1]
    
    # 변동률 계산
    change_pct = ((current_price - open_price) / open_price) * 100
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
    dist_from_low = ((current_price - low_20d) / current_price) * 100

    # 1. 낙폭 원인 분석 (Drop Reason)
    if change_pct < -3.0 and vol_ratio > 1.5:
        drop_reason = "🚨 대량 거래 동반 투매 (Panic)"
    elif change_pct < -2.0:
        drop_reason = "📉 차익 실현 매물 출회"
    elif change_pct > 2.0:
        drop_reason = "🚀 강한 매수세 유입 (Bullish)"
    elif -1.0 <= change_pct <= 1.0:
        drop_reason = "💤 거래량 감소 및 횡보"
    else:
        drop_reason = "🔍 일반적인 시장 등락"

    # 2. 지지선 감지 (Support Level)
    if dist_from_low < 2.0:
        support_level = f"${round(low_20d, 2)} 바닥 테스트 중 (Testing)"
        status = "WATCH" # 바닥 확인 필요
    elif dist_from_low < 5.0:
        support_level = f"${round(low_20d, 2)} 지지선 근접 (Near Support)"
        status = "BUY" # 분할 매수 구간
    else:
        support_level = f"추세 상승 중 (Next Target: ${round(high_20d, 2)})"
        status = "HOLD"

    # 3. 뉴스 시뮬레이션 (Latest News) - 기술적 상황을 문장화
    if vol_ratio > 2.0:
        news = "기관/외국인 주도 추정 대량 거래 발생. 변동성 확대 주의."
    elif change_pct < -2.0:
        news = "거시 경제 불확실성 및 섹터 약세 영향으로 하방 압력 지속."
    elif change_pct > 2.0:
        news = "저가 매수세 유입되며 주요 이평선 회복 시도."
    else:
        news = "뚜렷한 방향성 없이 관망 심리 우세. 주요 이벤트 대기."

    return {
        "symbol": ticker,
        "status": status,
        "drop_reason": drop_reason,
        "support_level": support_level,
        "latest_news": news
    }

def run_engine():
    print(f">>> V12 Engine Running... {get_kst_time()}")
    try:
        # 시장 데이터 (헤더용)
        spy = yf.Ticker("SPY").history(period="5d")
        vix = yf.Ticker("^VIX").history(period="5d")
        spy_price = round(spy['Close'].iloc[-1], 2)
        vix_price = round(vix['Close'].iloc[-1], 2)
        
        status_data = {"status": "NORMAL", "spy_price": spy_price, "vix": vix_price, "last_update": get_kst_time()}
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(status_data, f, indent=4)

        # 개별 종목 분석
        reports = []
        tickers = " ".join(WATCHLIST)
        data = yf.download(tickers, period="1mo", group_by='ticker', progress=False)
        
        for symbol in WATCHLIST:
            try:
                if not data[symbol].empty:
                    report = analyze_technical(data[symbol], symbol)
                    reports.append(report)
            except: pass
            
        with open(REPORT_FILE, 'w', encoding='utf-8') as f:
            json.dump(reports, f, indent=4)
        print(f">>> Analysis Complete. {len(reports)} Reports Generated.")

    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    run_engine()
