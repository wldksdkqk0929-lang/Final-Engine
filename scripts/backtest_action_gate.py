import os
import math
from datetime import datetime, timedelta, date

import pandas as pd
import yfinance as yf


SYMBOLS = [
    "AAPL","MSFT","NVDA","AMZN","META","TSLA","AMD","AVGO","GOOGL",
    "JPM","BAC","XOM","CVX","UNH","LLY","COST","WMT"
]

DISTANCE_CAP_UPPER = 20.0
DISTANCE_CAP_LOWER = 0.0

PRICE_OK_MIN_DISTANCE = 5.0
FLOW_V2_VOL_MULT = 1.3
FLOW_V2_PERSIST_DAYS = 2

MONTHS_BACK = 6

OUT_DIR = "data/backtest"
os.makedirs(OUT_DIR, exist_ok=True)


def _to_float(x):
    if isinstance(x, pd.Series):
        x = x.iloc[0]
    try:
        return float(x)
    except Exception:
        return None


def _compute_flow_v2(hist: pd.DataFrame) -> bool:
    if hist is None or len(hist) < 25:
        return False

    vol = hist["Volume"]
    close = hist["Close"]

    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    if isinstance(vol, pd.DataFrame):
        vol = vol.iloc[:, 0]

    ma5_vol = vol.rolling(5).mean()
    ma20_vol = vol.rolling(20).mean()
    ma5_close = close.rolling(5).mean()
    ma20_close = close.rolling(20).mean()

    cond = (ma5_vol >= FLOW_V2_VOL_MULT * ma20_vol) & (ma5_close > ma20_close)

    if len(cond) < FLOW_V2_PERSIST_DAYS:
        return False

    return bool(cond.iloc[-FLOW_V2_PERSIST_DAYS:].all())


def _snapshot_for_symbol(df: pd.DataFrame, asof: pd.Timestamp) -> dict:
    row = {"date": asof.date()}

    if df is None or asof not in df.index:
        row.update({
            "distance_pct": None,
            "price_ok": False,
            "flow_v1": False,
            "flow_v2": False,
            "structure": "NOT_FORMED",
            "actionable": False,
        })
        return row

    hist = df.loc[:asof].tail(200)
    if len(hist) < 25:
        return row

    close = hist["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]

    last = _to_float(close.iloc[-1])
    low_6m = _to_float(close.min())

    if last is None or low_6m is None or low_6m <= 0:
        return row

    distance_pct = round((last - low_6m) / low_6m * 100.0, 2)

    price_ok = distance_pct >= PRICE_OK_MIN_DISTANCE

    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    flow_v1 = _to_float(ma5.iloc[-1]) > _to_float(ma20.iloc[-1])

    flow_v2 = _compute_flow_v2(hist)

    if price_ok and flow_v1:
        structure = "FORMED"
    elif price_ok:
        structure = "FORMING"
    else:
        structure = "NOT_FORMED"

    if structure in ("FORMING","FORMED"):
        if distance_pct > DISTANCE_CAP_UPPER or distance_pct < DISTANCE_CAP_LOWER:
            structure = "NOT_FORMED"

    actionable = structure == "FORMED" and flow_v2

    row.update({
        "distance_pct": distance_pct,
        "price_ok": price_ok,
        "flow_v1": flow_v1,
        "flow_v2": flow_v2,
        "structure": structure,
        "actionable": actionable,
    })
    return row


def main():
    end = pd.Timestamp(date.today())
    start = end - pd.DateOffset(months=MONTHS_BACK)

    fetch_start = (start - pd.Timedelta(days=220)).date().isoformat()
    fetch_end = (end + pd.Timedelta(days=15)).date().isoformat()

    data = {}
    for sym in SYMBOLS:
        df = yf.download(sym, start=fetch_start, end=fetch_end, progress=False)
        if df is not None and not df.empty:
            df = df[["Close","Volume"]].dropna()
        data[sym] = df

    rows = []
    dates = data[SYMBOLS[0]].index
    dates = dates[(dates >= start) & (dates <= end)]

    for d in dates:
        for sym in SYMBOLS:
            snap = _snapshot_for_symbol(data[sym], d)
            snap["symbol"] = sym
            rows.append(snap)

    out = pd.DataFrame(rows)

    act = out[out["actionable"] == True]

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out.to_csv(f"{OUT_DIR}/backtest_full_{ts}.csv", index=False)
    act.to_csv(f"{OUT_DIR}/actionable_{ts}.csv", index=False)

    print("\n===== A안 소급 검증 결과 =====")
    print(f"기간: {start.date()} ~ {end.date()}")
    print(f"ACTIONABLE EVENTS: {len(act)}")
    if len(act):
        print(act.groupby("symbol").size())


if __name__ == "__main__":
    main()
