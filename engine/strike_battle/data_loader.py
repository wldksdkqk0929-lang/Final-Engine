from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import yfinance as yf

@dataclass
class LoadConfig:
    lookback_days: int = 365
    auto_adjust: bool = True

def load_price_data(symbol: str, cfg: Optional[LoadConfig] = None) -> Optional[pd.DataFrame]:
    if cfg is None: cfg = LoadConfig()
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="2y", interval="1d", auto_adjust=cfg.auto_adjust)
        if df.empty: return None
        return df
    except Exception:
        return None