from __future__ import annotations

from engine.strike.universe import load_universe
from engine.strike.data_loader import load_price_data
from engine.strike.strike_logic import is_strike_candidate
from engine.strike.report import print_report


def main():
    symbols = load_universe()
    results = []

    for sym in symbols:
        df = load_price_data(sym)
        if df is None:
            continue

        # Inject symbol without changing logic signature
        try:
            setattr(df, "_strike_symbol", sym)
        except Exception:
            pass

        hit = is_strike_candidate(df)
        if hit:
            # Ensure symbol populated
            if not hit.get("symbol"):
                hit["symbol"] = sym
            results.append(hit)

    print_report(results)


if __name__ == "__main__":
    main()
