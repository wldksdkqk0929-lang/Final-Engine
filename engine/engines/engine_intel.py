from engine.intel.connectors.intel_data_connector import fetch_intel_features

# Phase-6C FINAL FIX
DISTANCE_CAP_UPPER = 20.0
DISTANCE_CAP_LOWER = 0.0


class IntelEngine:
    """
    Phase-6C Structure Engine (FINAL FIXED)
    - Deterministic
    - Distance gate applied to FORMING + FORMED
    - Lower/Upper bound enforced
    """

    def analyze_symbol(self, symbol: str):
        features = fetch_intel_features(symbol)

        structure = features.get("structure", "NOT_FORMED")
        price_ok = features.get("price_ok", False)
        flow_ok = features.get("flow_ok", False)
        distance_pct = features.get("distance_pct")
        watch = features.get("watch", False)

        # 🔒 Phase-6C FINAL: Distance gate (upper + lower)
        if (
            structure in ("FORMING", "FORMED")
            and distance_pct is not None
            and (
                distance_pct > DISTANCE_CAP_UPPER
                or distance_pct < DISTANCE_CAP_LOWER
            )
        ):
            structure = "NOT_FORMED"

        return {
            "symbol": symbol,
            "structure": structure,
            "price_ok": price_ok,
            "flow_ok": flow_ok,
            "support_distance_pct": distance_pct,
            "watchlist": watch,
            "raw": features,
        }
