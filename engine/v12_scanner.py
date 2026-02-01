import yfinance as yf
import pandas as pd
import json
import sys

# 감시 대상 (정식 리스트)
TARGETS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", 
    "AMD", "INTC", "PLTR", "SOFI", "PYPL", "NFLX", "COIN",
    "MARA", "RIOT", "DKNG", "HOOD", "RIVN", "LCID"
]

class MarketScanner:
    def __init__(self):
        print("📡 Radar Activated (Real Mode).")

    def check_and_report_market(self):
        print("\n🛡️ [STEP 0] Checking Market Regime (REAL)...")
        status_report = {
            "status": "SAFE",
            "message": "Market is Healthy",
            "regime": "BULL MARKET", 
            "spy_price": 0, "spy_ma": 0, "vix": 0,
            "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        try:
            market_data = yf.download(["SPY", "^VIX"], period="1y", interval="1d", progress=False)
            
            spy_close = market_data["Close"]["SPY"]
            spy_200ma = spy_close.rolling(window=200).mean().iloc[-1]
            spy_current = spy_close.iloc[-1]
            vix_current = market_data["Close"]["^VIX"].iloc[-1]
            
            status_report["spy_price"] = round(spy_current, 2)
            status_report["spy_ma"] = round(spy_200ma, 2)
            status_report["vix"] = round(vix_current, 2)

            # 판정 로직 (정상 기준)
            reasons = []
            if spy_current < spy_200ma:
                reasons.append("SPY Broken")
                status_report["regime"] = "BEAR MARKET"
            
            if vix_current > 35:
                reasons.append("Panic VIX")
                status_report["regime"] = "PANIC"

            if reasons:
                status_report["status"] = "DANGER"
                status_report["message"] = " & ".join(reasons)
                print(f"   ⛔ MARKET DANGER: {status_report['message']}")
            else:
                print("   ✅ MARKET GREEN")

        except Exception as e:
            print(f"Error: {e}")
            status_report["status"] = "DANGER" # 데이터 없으면 위험으로 간주
            status_report["message"] = "Data Check Failed"

        with open("market_status.json", "w") as f:
            json.dump(status_report, f, indent=4)
            
        return status_report["status"] == "SAFE"

    def calculate_rsi(self, series, period=14):
        delta = series.diff(1)
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def scan(self):
        # 시장 확인
        is_safe = self.check_and_report_market()
        
        candidates = []
        if not is_safe:
            # 시장 위험 시 스캔 중단 (빈 리스트 저장)
            with open("targets.json", "w") as f: json.dump([], f)
            return []

        # 개별 종목 스캔
        print(f"\n📡 [STEP 1] Scanning Targets...")
        data = yf.download(TARGETS, period="6mo", interval="1d", progress=False)
        
        for symbol in TARGETS:
            try:
                if len(TARGETS) == 1: df = data
                else: df = data.xs(symbol, axis=1, level=1) if isinstance(data.columns, pd.MultiIndex) else data
                
                if len(df) < 20: continue

                current = df['Close'].iloc[-1]
                high = df['High'].max()
                drawdown = ((current - high) / high) * 100
                rsi = self.calculate_rsi(df['Close']).iloc[-1]
                
                vol_avg = df['Volume'].iloc[-20:-1].mean()
                vol_now = df['Volume'].iloc[-1]
                vol_ratio = (vol_now / vol_avg * 100) if vol_avg > 0 else 0

                is_target = False
                status = "PASS"
                if drawdown < -5.0:
                    if rsi < 45: is_target = True; status = "OVERSOLD"
                    elif vol_ratio > 120: is_target = True; status = "VOL_SPIKE"
                
                if is_target:
                    print(f"   🎯 {symbol}: Drop {drawdown:.1f}%")
                    candidates.append({
                        "symbol": symbol, "status": status, 
                        "drawdown": round(drawdown, 2), "rsi": round(rsi, 1), "vol_ratio": round(vol_ratio, 0)
                    })
            except: continue

        with open("targets.json", "w") as f:
            json.dump(candidates, f, indent=4)
        return candidates

if __name__ == "__main__":
    MarketScanner().scan()
