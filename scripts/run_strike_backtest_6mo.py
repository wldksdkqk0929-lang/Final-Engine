from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Tuple

import pandas as pd

from engine.strike.universe import load_universe
from engine.strike.data_loader import load_price_data_range
from engine.strike.strike_logic import is_strike_candidate


def _utc_today_date() -> datetime:
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


def _make_windows(end_date_utc: datetime, days: int = 183) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """
    Generate daily windows for backtest.
    For each target day D, we need enough history to compute:
      - MA20
      - 10-day volume avg
      - 63-day low window
      - breakout prev5
    So we fetch ~120 trading days buffer.
    """
    windows: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    for i in range(days):
        day_end = end_date_utc - timedelta(days=i)
        # fetch buffer: ~200 calendar days back to cover 63 trading days safely
        start = pd.Timestamp((day_end - timedelta(days=220)).date().isoformat())
        end = pd.Timestamp((day_end + timedelta(days=1)).date().isoformat())
        windows.append((start, end))
    windows.reverse()  # oldest -> newest
    return windows


def main():
    symbols = load_universe()
    end_utc = _utc_today_date()
    windows = _make_windows(end_utc, days=183)

    fired_days: List[Dict[str, Any]] = []
    total_days = 0

    # For speed: we run day-by-day but reuse the same downloaded frame per symbol per day window.
    # This is intentionally brute-force v1; performance tuning is Phase-6H.
    for (start, end) in windows:
        day = (end - pd.Timedelta(days=1)).date().isoformat()
        hits = 0

        for sym in symbols:
            df = load_price_data_range(sym, start_end=(start, end))
            if df is None or df.empty:
                continue

            # keep only up to that day (end is next day already)
            # df index is datetime-like; slice safe
            df2 = df.loc[:pd.Timestamp(day)]
            if df2 is None or df2.empty:
                continue

            try:
                setattr(df2, "_strike_symbol", sym)
            except Exception:
                pass

            hit = is_strike_candidate(df2)
            if hit:
                hits += 1

        total_days += 1
        if hits > 0:
            fired_days.append({"date": day, "hits": hits})

        print(f"{day} | hits={hits}")

    print("\n=== Strike Fired Days (last ~6mo) ===")
    if not fired_days:
        print("NONE (0 days)")
        return

    # Sort by hits DESC then date ASC
    fired_days.sort(key=lambda x: (-int(x["hits"]), x["date"]))

    for r in fired_days:
        print(f'{r["date"]} | hits={r["hits"]}')

    print(f"\nTotal days scanned: {total_days}")
    print(f"Days with >=1 hit: {len(fired_days)}")


if __name__ == "__main__":
    main()
