import yfinance as yf
import json
import os
import datetime
import pandas as pd

# [설정]
WATCHLIST = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]
VIX_THRESHOLD = 35.0
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(BASE_DIR, 'market_status.json')

def get_kst_time():
    # UTC 시간에서 9시간을 더해 한국 시간(KST) 생성
    utc_now = datetime.datetime.utcnow()
    kst_now = utc_now + datetime.timedelta(hours=9)
    return kst_now.strftime("%Y-%m-%d %H:%M:%S (KST)")

def calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_engine():
    print(f">>> Engine Running... (Time: {get_kst_time()})")
    
    try:
        # 데이터 수집
        spy = yf.Ticker("SPY").history(period="1y")
        vix = yf.Ticker("^VIX").history(period="5d")
        
        current_spy = round(spy['Close'].iloc[-1], 2)
        current_vix = round(vix['Close'].iloc[-1], 2)
        ma_200 = spy['Close'].rolling(window=200).mean().iloc[-1]
        
        # 상태 판단
        status = "NORMAL"
        if current_vix >= VIX_THRESHOLD or current_spy < ma_200:
            status = "DANGER"

        # 타겟 스캔
        targets = []
        if status == "NORMAL":
            tickers = " ".join(WATCHLIST)
            data = yf.download(tickers, period="1mo", group_by='ticker', progress=False)
            
            for symbol in WATCHLIST:
                try:
                    df = data[symbol]
                    if df.empty: continue
                    close_price = df['Close'].iloc[-1]
                    volume = df['Volume'].iloc[-1] if not pd.isna(df['Volume'].iloc[-1]) else 0
                    rsi_series = calculate_rsi(df['Close'])
                    current_rsi = round(rsi_series.iloc[-1], 1)
                    
                    targets.append({
                        "ticker": symbol,
                        "price": round(float(close_price), 2),
                        "rsi": float(current_rsi),
                        "volume": f"{int(volume):,}",
                        "sector": "Tech/Growth"
                    })
                except: pass

        # 결과 저장 (한국 시간 포함)
        output = {
            "status": status,
            "spy_price": current_spy,
            "vix": current_vix,
            "targets": targets,
            "last_update": get_kst_time()  # <--- 한국 시간 저장
        }

        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4)
            
        print(">>> Market Data Updated.")

    except Exception as e:
        print(f"[ERROR] {str(e)}")

if __name__ == "__main__":
    run_engine()
