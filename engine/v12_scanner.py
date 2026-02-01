import yfinance as yf
import pandas as pd
import numpy as np
import time

# 감시 대상 (테스트용 우량주 + 변동성 종목 혼합)
TARGETS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", 
    "AMD", "INTC", "PLTR", "SOFI", "PYPL", "NFLX", "COIN",
    "MARA", "RIOT", "DKNG", "HOOD", "RIVN", "LCID"
]

class MarketScanner:
    def __init__(self):
        print(f"📡 Radar Activated. Scanning {len(TARGETS)} targets...")

    def calculate_rsi(self, series, period=14):
        delta = series.diff(1)
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def scan(self):
        candidates = []
        
        # 데이터 일괄 다운로드 (속도 최적화)
        data = yf.download(TARGETS, period="6mo", interval="1d", progress=False)
        
        print(f"📊 Data Acquired. Analyzing patterns...\n")
        print(f"{'SYMBOL':<8} | {'DROP(%)':<8} | {'RSI':<6} | {'VOL(%)':<8} | {'STATUS'}")
        print("-" * 55)

        for symbol in TARGETS:
            try:
                # 데이터 추출
                if len(TARGETS) == 1:
                    df = data
                else:
                    df = data.xs(symbol, axis=1, level=1) if isinstance(data.columns, pd.MultiIndex) else data

                # 데이터 부족 시 스킵
                if len(df) < 20: continue

                # 1. 현재가 및 고점 대비 하락률 (Deep Dive Check)
                current_price = df['Close'].iloc[-1]
                high_52 = df['High'].max()
                drawdown = ((current_price - high_52) / high_52) * 100

                # 2. RSI 계산 (Oversold Check)
                rsi_series = self.calculate_rsi(df['Close'])
                rsi = rsi_series.iloc[-1]

                # 3. 거래량 급증 (Volume Spike Check)
                avg_vol = df['Volume'].iloc[-20:-1].mean() # 최근 20일 평균 (오늘 제외)
                today_vol = df['Volume'].iloc[-1]
                
                if avg_vol == 0: continue
                vol_ratio = (today_vol / avg_vol) * 100

                # --- 🎯 [V12 필터링 로직] ---
                # 조건: 고점대비 -10% 이상 하락 AND (RSI < 45 OR 거래량 120% 폭발)
                # (테스트를 위해 조건을 조금 넓게 잡았습니다)
                is_target = False
                status = "PASS"
                
                if drawdown < -5.0: # 최소 5%는 빠져야 쳐다봄
                    if rsi < 45: # 과매도권 진입
                        is_target = True
                        status = "OVERSOLD"
                    elif vol_ratio > 120: # 바닥권 거래량 터짐
                        is_target = True
                        status = "VOL_SPIKE"
                
                # 결과 출력
                if is_target:
                    print(f"🎯 {symbol:<6} | {drawdown:>6.2f}%  | {rsi:>5.1f}  | {vol_ratio:>6.0f}%  | {status}")
                    candidates.append({
                        "symbol": symbol,
                        "status": status,
                        "drawdown": round(drawdown, 2),
                        "rsi": round(rsi, 1),
                        "vol_ratio": round(vol_ratio, 0)
                    })
                else:
                    # 탈락한 애들은 흐리게 출력 (로그 확인용)
                    pass 

            except Exception as e:
                # 데이터 에러나면 무시
                continue

        print("-" * 55)
        print(f"✅ Scan Complete. {len(candidates)} candidates identified.")
        return candidates

if __name__ == "__main__":
    scanner = MarketScanner()
    results = scanner.scan()
    
    # 결과를 파일로 저장 (Inspector가 읽을 수 있게)
    import json
    with open("targets.json", "w") as f:
        json.dump(results, f, indent=4)
