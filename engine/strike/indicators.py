from __future__ import annotations

import pandas as pd


def calc_distance(close_series: pd.Series) -> float:
    """
    Distance = (현재가 - 3개월 최저가) / 최저가
    - 3개월: 최근 약 63 거래일 기준
    Return ratio (e.g., 0.124 for 12.4%)
    """
    if close_series is None or close_series.empty:
        return float("nan")

    close = close_series.dropna()
    if close.empty:
        return float("nan")

    window = close.tail(63)
    if window.empty:
        return float("nan")

    low_3m = window.min()
    last = window.iloc[-1]
    if low_3m <= 0:
        return float("nan")

    return float((last - low_3m) / low_3m)


def calc_flow_v1(close_series: pd.Series) -> bool:
    """
    Flow v1: MA(5) > MA(20)
    """
    if close_series is None or close_series.empty:
        return False

    close = close_series.dropna()
    if len(close) < 20:
        return False

    ma5 = close.rolling(5).mean().iloc[-1]
    ma20 = close.rolling(20).mean().iloc[-1]
    if pd.isna(ma5) or pd.isna(ma20):
        return False

    return bool(ma5 > ma20)


def calc_volume_shock(volume_series: pd.Series) -> float:
    """
    Volume Shock ratio = 오늘 거래량 / 최근 10일 평균
    """
    if volume_series is None or volume_series.empty:
        return float("nan")

    vol = volume_series.dropna()
    if len(vol) < 11:
        return float("nan")

    today = vol.iloc[-1]
    avg10 = vol.iloc[-11:-1].mean()
    if avg10 <= 0:
        return float("nan")

    return float(today / avg10)


def calc_breakout(close_series: pd.Series) -> bool:
    """
    Price Breakout: 오늘 종가 > 직전 5거래일 고가(=종가 기준)
    - 스펙에 '직전 5거래일 고가'만 명시되어 있어, Close 기반으로 구현.
      (필요 시 High 기반으로 바꾸면 스펙 위반이므로 그대로 둠)
    """
    if close_series is None or close_series.empty:
        return False

    close = close_series.dropna()
    if len(close) < 6:
        return False

    today_close = close.iloc[-1]
    prev5_high = close.iloc[-6:-1].max()
    if pd.isna(today_close) or pd.isna(prev5_high):
        return False

    return bool(today_close > prev5_high)
