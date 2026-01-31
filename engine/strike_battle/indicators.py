from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class Features:
    symbol: str
    date: pd.Timestamp
    close: float
    high: float
    low: float
    volume: float
    volume_ratio: float
    distance_pct: float
    ret1d_pct: float
    flow_v1: bool
    breakout_high: bool

def compute_features_for_date(symbol: str, df: pd.DataFrame, date: pd.Timestamp) -> Optional[Features]:
    if date not in df.index: return None
    idx = df.index.get_loc(date)
    if isinstance(idx, slice): idx = idx.stop - 1
    if idx < 60: return None 

    sub = df.iloc[:idx+1]
    
    close = float(sub["Close"].iloc[-1])
    high = float(sub["High"].iloc[-1])
    low = float(sub["Low"].iloc[-1])
    vol = float(sub["Volume"].iloc[-1])
    
    vol_avg = sub["Volume"].iloc[-11:-1].mean()
    vol_ratio = vol / vol_avg if vol_avg > 0 else 0.0
    
    low_60 = sub["Low"].iloc[-61:].min()
    dist_pct = (close - low_60) / low_60 * 100 if low_60 > 0 else 999.0
    
    ma5 = sub["Close"].iloc[-5:].mean()
    ma20 = sub["Close"].iloc[-20:].mean()
    flow = ma5 > ma20
    
    prev_high = sub["High"].iloc[-6:-1].max()
    breakout = high > prev_high
    
    if len(sub) > 1:
        prev_close = sub["Close"].iloc[-2]
        ret = (close / prev_close - 1.0) * 100 if prev_close > 0 else 0.0
    else:
        ret = 0.0

    return Features(symbol, date, close, high, low, vol, vol_ratio, dist_pct, ret, flow, breakout)