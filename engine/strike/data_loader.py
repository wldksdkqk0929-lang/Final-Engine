from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

try:
    import yfinance as yf
except Exception:
    yf = None


def _normalize_ohlcv(df: pd.DataFrame, symbol: str) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None

    # MultiIndex columns
    if isinstance(df.columns, pd.MultiIndex):
        cols = {}
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            if (c, symbol) in df.columns:
                cols[c] = (c, symbol)
        if len(cols) < 5:
            return None
        df = df[list(cols.values())].copy()
        df.columns = list(cols.keys())
    else:
        needed = ["Open", "High", "Low", "Close", "Volume"]
        if not all(c in df.columns for c in needed):
            return None
        df = df[needed].copy()

    return df


def _coerce_clean(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["Close", "Volume"])
    if df.empty:
        return None

    # tz-naive index
    try:
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_convert(None)
    except Exception:
        pass

    # Ensure sorted
    try:
        df = df.sort_index()
    except Exception:
        pass

    return df


def load_price_data(symbol: str) -> Optional[pd.DataFrame]:
    """
    Default: last ~6 months of daily OHLCV (using period).
    """
    return load_price_data_range(symbol, period="6mo")


def load_price_data_range(
    symbol: str,
    *,
    period: Optional[str] = None,
    start_end: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> Optional[pd.DataFrame]:
    """
    Range loader:
    - period="6mo" (default) OR
    - start_end=(start_ts, end_ts) (preferred for backtest determinism)
    """
    if yf is None:
        raise RuntimeError("yfinance not installed. Install: pip install yfinance")

    sym = symbol.strip().upper()
    if not sym:
        return None

    try:
        if start_end is not None:
            start_ts, end_ts = start_end
            raw = yf.download(
                sym,
                start=start_ts.date().isoformat(),
                end=end_ts.date().isoformat(),
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        else:
            raw = yf.download(
                sym,
                period=period or "6mo",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
    except Exception:
        return None

    df = _normalize_ohlcv(raw, sym)
    df = _coerce_clean(df)
    return df
