from __future__ import annotations

from typing import List, Dict, Any


def _safe_float(x, default=0.0) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def print_report(results: List[Dict[str, Any]]) -> None:
    """
    Output fields (fixed):
    Symbol | Distance% | VolumeRatio | Breakout

    Sorting:
    1) VolumeRatio DESC
    2) Distance ASC
    Top 20
    """
    if not results:
        print("Symbol | Distance% | VolumeRatio | Breakout")
        return

    # Normalize and filter
    cleaned = []
    for r in results:
        if not isinstance(r, dict):
            continue
        cleaned.append(
            {
                "symbol": str(r.get("symbol", "")).upper(),
                "distance_pct": _safe_float(r.get("distance_pct", 0.0)),
                "volume_ratio": _safe_float(r.get("volume_ratio", 0.0)),
                "breakout": bool(r.get("breakout", False)),
            }
        )

    cleaned.sort(key=lambda x: (-x["volume_ratio"], x["distance_pct"]))

    print("Symbol | Distance% | VolumeRatio | Breakout")
    for r in cleaned[:20]:
        sym = r["symbol"]
        dist = f'{r["distance_pct"]:.1f}'
        vr = f'{r["volume_ratio"]:.2f}'
        bo = "True" if r["breakout"] else "False"
        print(f"{sym} | {dist} | {vr} | {bo}")
