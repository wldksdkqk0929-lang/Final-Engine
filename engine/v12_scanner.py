import yfinance as yf
import pandas as pd
import json
import sys

TARGETS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", 
    "AMD", "INTC", "PLTR", "SOFI", "PYPL", "NFLX", "COIN",
    "MARA", "RIOT", "DKNG", "HOOD", "RIVN", "LCID"
]

class MarketScanner:
    def __init__(self):
        print("📡 Radar Activated (V13.1).")

    def check_and_report_market(self):
        print("\n🛡️ [STEP 0] Checking Market Regime...")
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
            else:
                print("   ✅ MARKET GREEN")

        except Exception as e:
            print(f"Error: {e}")
            status_report["status"] = "DANGER"
            status_report["message"] = "Data Check Failed"

        with open("market_status.json", "w") as f:
            json.dump(status_report, f, indent=4)
            
        return status_report["status"] == "SAFE"

    def scan(self):
        is_safe = self.check_and_report_market()
        candidates = []
        
        # 시장이 위험하면 스캔 중단
        if not is_safe:
            with open("targets.json", "w") as f: json.dump([], f)
            return []

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
                
                delta = df['Close'].diff(1)
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rsi = (100 - (100 / (1 + (gain / loss)))).iloc[-1]
                
                vol_avg = df['Volume'].iloc[-20:-1].mean()
                vol_now = df['Volume'].iloc[-1]
                vol_ratio = (vol_now / vol_avg * 100) if vol_avg > 0 else 0

                is_target = False
                status = "PASS"
                if drawdown < -5.0:
                    if rsi < 45: is_target = True; status = "OVERSOLD"
                    elif vol_ratio > 120: is_target = True; status = "VOL_SPIKE"
                
                if is_target:
                    candidates.append({
                        "symbol": symbol, "status": status, 
                        "drawdown": round(drawdown, 2), "rsi": round(rsi, 1), "vol_ratio": round(vol_ratio, 0)
                    })
            except: continue

        with open("targets.json", "w") as f: json.dump(candidates, f, indent=4)
        return candidates

if __name__ == "__main__":
    MarketScanner().scan()
