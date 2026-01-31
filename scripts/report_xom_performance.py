import glob
import pandas as pd

# 최신 full backtest 파일 선택
files = sorted(glob.glob("data/backtest/backtest_full_*.csv"))
if not files:
    raise SystemExit("No backtest_full file found.")

df = pd.read_csv(files[-1])
df["date"] = pd.to_datetime(df["date"])

# XOM Actionable 이벤트만 추출
xom_events = df[(df["symbol"] == "XOM") & (df["actionable"] == True)].copy()
if xom_events.empty:
    raise SystemExit("No XOM actionable events found.")

print("\n======================================")
print("📌 XOM ACTIONABLE PERFORMANCE REPORT")
print("======================================\n")

for _, ev in xom_events.iterrows():
    d0 = ev["date"]

    future = df[(df["symbol"] == "XOM") & (df["date"] > d0)].sort_values("date")

    def ret_after(n):
        if len(future) < n:
            return None
        c0 = ev["distance_pct"]
        return future.iloc[n-1]["distance_pct"]

    # 가격 데이터는 full 파일에 없으므로 yfinance로 직접 재조회
    import yfinance as yf
    hist = yf.download("XOM", start=d0.strftime("%Y-%m-%d"), period="30d", progress=False)

    closes = hist["Close"]
    if isinstance(closes, pd.DataFrame):
        closes = closes.iloc[:,0]

    if len(closes) < 21:
        print(f"▶ {d0.date()} : 이후 데이터 부족")
        continue

    c0 = closes.iloc[0]
    r5 = round((closes.iloc[5] / c0 - 1) * 100, 2)
    r10 = round((closes.iloc[10] / c0 - 1) * 100, 2)
    r20 = round((closes.iloc[20] / c0 - 1) * 100, 2)

    mdd = round((closes.min() / c0 - 1) * 100, 2)

    print(f"▶ Actionable Date : {d0.date()}")
    print(f"  Distance (%)    : {ev['distance_pct']}")
    print(f"  +5D Return (%)  : {r5}")
    print(f"  +10D Return (%) : {r10}")
    print(f"  +20D Return (%) : {r20}")
    print(f"  Max Drawdown %  : {mdd}")
    print("-" * 35)

print(f"\n총 Actionable 횟수: {len(xom_events)}")
