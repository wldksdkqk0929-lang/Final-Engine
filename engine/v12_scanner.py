import yfinance as yf
import json
import os
import datetime
import pandas as pd

# [설정] 감시 대상 및 기준
WATCHLIST = ["TSLA", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL"]
VIX_THRESHOLD = 35.0
RSI_PERIOD = 14

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS_FILE = os.path.join(BASE_DIR, 'market_status.json')

def calculate_rsi(series, period=14):
    delta = series.diff(1)
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def run_engine():
    print(f">>> Sniper Engine V12.2 Started at {datetime.datetime.now()}")
    
    try:
        # 1. 시장 지표 수집
        spy = yf.Ticker("SPY").history(period="1y")
        vix = yf.Ticker("^VIX").history(period="5d")
        
        current_spy = round(spy['Close'].iloc[-1], 2)
        current_vix = round(vix['Close'].iloc[-1], 2)
        ma_200 = spy['Close'].rolling(window=200).mean().iloc[-1]
        
        # 2. 시장 상태 판단
        status = "NORMAL"
        if current_vix >= VIX_THRESHOLD or current_spy < ma_200:
            status = "DANGER"
            print(f"!!! RED ALERT: Market Unstable (VIX: {current_vix}) !!!")

        # 3. 타겟 스캔 (NORMAL일 때만 가동)
        targets = []
        if status == "NORMAL":
            print(f">>> Market Stable. Scanning {len(WATCHLIST)} Targets...")
            
            # 한 번에 다운로드하여 속도 향상
            tickers = " ".join(WATCHLIST)
            data = yf.download(tickers, period="1mo", group_by='ticker', progress=False)
            
            for symbol in WATCHLIST:
                try:
                    df = data[symbol]
                    if df.empty: continue
                    
                    # 지표 계산
                    close_price = df['Close'].iloc[-1]
                    # volume이 0이거나 NaN인 경우 처리
                    volume = df['Volume'].iloc[-1] if not pd.isna(df['Volume'].iloc[-1]) else 0
                    
                    # RSI 계산 (간이)
                    rsi_series = calculate_rsi(df['Close'])
                    current_rsi = round(rsi_series.iloc[-1], 1)
                    
                    # 결과 등록
                    targets.append({
                        "ticker": symbol,
                        "price": round(float(close_price), 2),
                        "rsi": float(current_rsi),
                        "volume": f"{int(volume):,}", # 천단위 콤마
                        "sector": "Tech/Growth" # 임시 구분
                    })
                except Exception as e:
                    print(f"Skipping {symbol}: {e}")
        else:
            print(">>> Skipping Scan due to DANGER status.")

        # 4. 결과 저장
        output = {
            "status": status,
            "spy_price": current_spy,
            "vix": current_vix,
            "targets": targets,
            "last_update": str(datetime.datetime.now())
        }

        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=4)
            
        print(f">>> Scan Complete. Found {len(targets)} targets.")

    except Exception as e:
        print(f"[CRITICAL ERROR] {str(e)}")

if __name__ == "__main__":
    run_engine()
