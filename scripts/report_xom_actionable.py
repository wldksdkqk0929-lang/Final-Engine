import glob
import pandas as pd

# 가장 최근 actionable 파일 자동 선택
files = sorted(glob.glob("data/backtest/actionable_*.csv"))
if not files:
    raise SystemExit("No actionable file found.")

df = pd.read_csv(files[-1])

xom = df[df["symbol"] == "XOM"].copy()
if xom.empty:
    raise SystemExit("No XOM actionable events found.")

# 날짜 기준 정렬
xom = xom.sort_values("date")

print("\n==============================")
print("📌 XOM ACTIONABLE EVENT REPORT")
print("==============================\n")

for i, row in xom.iterrows():
    print(f"▶ Actionable Date : {row['date']}")
    print(f"  Structure       : {row['structure']}")
    print(f"  Distance (%)    : {row['distance_pct']}")
    print(f"  Price OK        : {row['price_ok']}")
    print(f"  Flow v1         : {row['flow_v1']}")
    print(f"  Flow v2 (Gate)  : {row['flow_v2']}")
    print(f"  +5D Return (%)  : {row.get('ret_5d_pct')}")
    print(f"  +10D Return (%) : {row.get('ret_10d_pct')}")
    print(f"  +20D Return (%) : {row.get('ret_20d_pct', 'N/A')}")
    print("-" * 30)

print(f"\n총 Actionable 횟수: {len(xom)}")
