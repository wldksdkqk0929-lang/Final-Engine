from __future__ import annotations

import csv
import os
from typing import List

try:
    import pandas as pd
except Exception:
    pd = None

try:
    import yfinance as yf
except Exception:
    yf = None


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items:
        x = x.strip().upper()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _load_from_csv(path: str) -> List[str]:
    symbols: List[str] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                symbols.append(row[0])
    return _dedupe_keep_order(symbols)


def _load_from_wikipedia() -> List[str]:
    if pd is None:
        return []

    symbols: List[str] = []

    try:
        sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        symbols.extend(sp500["Symbol"].astype(str).tolist())
    except Exception:
        pass

    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
        picked = None
        for t in tables:
            cols = [c.lower() for c in t.columns.astype(str)]
            if any("ticker" in c or "symbol" in c for c in cols):
                picked = t
                break
        if picked is not None:
            for c in picked.columns.astype(str):
                if "ticker" in c.lower() or "symbol" in c.lower():
                    symbols.extend(picked[c].astype(str).tolist())
                    break
    except Exception:
        pass

    return _dedupe_keep_order([s.replace(".", "-") for s in symbols])


def _load_from_yfinance_index() -> List[str]:
    """
    Fallback: yfinance index constituents
    - ^GSPC (S&P500)
    - ^NDX (Nasdaq100)
    """
    if yf is None:
        return []

    symbols: List[str] = []

    for idx in ["^GSPC", "^NDX"]:
        try:
            tickers = yf.Tickers(idx).tickers
            symbols.extend(list(tickers.keys()))
        except Exception:
            pass

    return _dedupe_keep_order(symbols)


def load_universe() -> list[str]:
    """
    Universe loading priority:
    1. STRIKE_UNIVERSE_CSV (explicit)
    2. Wikipedia (pandas.read_html)
    3. yfinance index fallback (Codespaces-safe)

    Hard failure only if all methods fail.
    """

    csv_path = os.getenv("STRIKE_UNIVERSE_CSV", "").strip()
    if csv_path:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"STRIKE_UNIVERSE_CSV not found: {csv_path}")
        return _load_from_csv(csv_path)

    symbols = _load_from_wikipedia()
    if symbols:
        return symbols

    symbols = _load_from_yfinance_index()
    if symbols:
        return symbols

    raise RuntimeError(
        "Universe load failed: CSV / Wikipedia / yfinance index all unavailable"
    )
