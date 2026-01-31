"""
Intel Data Connector — Phase-6D (Observation)
- Adds Flow v2 (quality flow) for observation only
- Does NOT change structure decision
"""

import yfinance as yf
import pandas as pd


def _flow_v2(hist: pd.DataFrame) -> bool:
    """
    Flow v2 (Observation):
    1) Volume participation: MA5(vol) >= 1.3 * MA20(vol)
    2) Trend turn: MA5(close) > MA20(close)
    3) Persistence: conditions hold for >= 2 consecutive days
    """
    try:
        if hist is None or hist.empty or len(hist) < 25:
            return False

        vol = hist["Volume"]
        close = hist["Close"]

        ma5_vol = vol.rolling(5).mean()
        ma20_vol = vol.rolling(20).mean()

        ma5_close = close.rolling(5).mean()
        ma20_close = close.rolling(20).mean()

        cond_vol = ma5_vol >= 1.3 * ma20_vol
        cond_trend = ma5_close > ma20_close

        cond = cond_vol & cond_trend

        # Persistence: last 2 days both True
        return bool(cond.iloc[-1] and cond.iloc[-2])
    except Exception:
        return False


def fetch_intel_features(symbol: str) -> dict:
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="6mo")

        if hist.empty:
            raise ValueError("No market data")

        close = hist["Close"]
        last = close.iloc[-1]
        low_6m = close.min()

        distance_pct = round((last - low_6m) / low_6m * 100, 2)

        # Existing (v1) signals — keep behavior
        price_ok = distance_pct >= 5.0
        flow_ok = close.iloc[-5:].mean() > close.iloc[-20:].mean()

        # Structure (pre-engine)
        if price_ok and flow_ok:
            structure = "FORMED"
        elif price_ok:
            structure = "FORMING"
        else:
            structure = "NOT_FORMED"

        return {
            "structure": structure,
            "price_ok": price_ok,
            "flow_ok": flow_ok,          # v1 (legacy)
            "flow_v2": _flow_v2(hist),   # v2 (observation)
            "distance_pct": distance_pct,
            "watch": False,
        }

    except Exception:
        return {
            "structure": "NOT_FORMED",
            "price_ok": False,
            "flow_ok": False,
            "flow_v2": False,
            "distance_pct": None,
            "watch": False,
        }
