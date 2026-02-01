import yfinance as yf
import json
import time
import os

# 데이터 저장 경로
STATUS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'market_status.json')

print("--- SNIPER ENGINE V12 START ---")
print(f"Target File: {STATUS_FILE}")

# 1. SPY & VIX 데이터 수집
print("Fetching SPY & VIX data...")
spy = yf.Ticker("SPY").history(period="1d")
vix = yf.Ticker("^VIX").history(period="1d")

current_spy = round(spy['Close'].iloc[-1], 2)
current_vix = round(vix['Close'].iloc[-1], 2)

print(f"SPY: {current_spy}, VIX: {current_vix}")

# 2. 시장 상태 판단 (Red Alert 로직)
status = "NORMAL"
if current_vix >= 35:
    status = "DANGER"

# 3. JSON 파일 업데이트
data = {
    "status": status,
    "spy_price": current_spy,
    "vix": current_vix,
    "targets": [] # 종목 스캔 로직은 추후 연결
}

with open(STATUS_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=4)

print(">>> Market Status Updated Successfully.")
