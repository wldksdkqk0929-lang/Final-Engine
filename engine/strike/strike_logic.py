from __future__ import annotations

from typing import Optional, Dict, Any

import pandas as pd

from engine.strike.indicators import (
    calc_breakout,
    calc_distance,
    calc_flow_v1,
    calc_volume_shock,
)


# === Phase-6H Parameters (FIXED) ===
VOLUME_SHOCK_MIN = 1.5     # was 2.0 in Phase-6G
DISTANCE_MIN = 0.05
DISTANCE_MAX = 0.40       # was 0.25 in Phase-6G
# ==================================


def is_strike_candidate(df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Phase-6H Strike 조건 (모두 충족):

    1) Breakout
       - 오늘 종가 > 직전 5거래일 종가 고점

    2) Volume Shock (v1)
       - 오늘 거래량 >= 최근 10일 평균 * 1.5

    3) Flow v1
       - MA(5) > MA(20)

    4) Distance (확장)
       - 5% <= (현재가 - 3개월 최저가) / 최저가 <= 40%
    """
    if df is None or df.empty:
        return None

    for c in ["Close", "Volume"]:
        if c not in df.columns:
            return None

    close = df["Close"]
    vol = df["Volume"]

    # 1) Breakout
    breakout = calc_breakout(close)
    if not breakout:
        return None

    # 2) Volume Shock
    volume_ratio = calc_volume_shock(vol)
    if pd.isna(volume_ratio) or volume_ratio < VOLUME_SHOCK_MIN:
        return None

    # 3) Flow v1
    if not calc_flow_v1(close):
        return None

    # 4) Distance
    dist = calc_distance(close)
    if pd.isna(dist):
        return None

    if dist < DISTANCE_MIN or dist > DISTANCE_MAX:
        return None

    symbol = getattr(df, "_strike_symbol", "") or ""

    return {
        "symbol": symbol,
        "distance_pct": round(dist * 100.0, 1),
        "volume_ratio": round(volume_ratio, 2),
        "breakout": True,
    }
