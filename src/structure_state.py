from dataclasses import dataclass
from typing import Dict


@dataclass
class StructureSignals:
    price_signal: bool
    flow_signal: bool
    support_distance_pct: float


class StructureState:
    NOT_FORMED = "NOT_FORMED"
    FORMING = "FORMING"
    FORMED = "FORMED"


def compute_price_signal(features: Dict) -> bool:
    """
    Price Signal:
    - Higher Low OR Reclaim
    """
    higher_low = features.get("higher_low", False)
    reclaim = features.get("reclaim", False)
    return bool(higher_low or reclaim)


def compute_flow_signal(features: Dict) -> bool:
    """
    Flow Signal:
    - Volume Dry-up (3d avg / 20d avg <= 0.5)
    """
    vol_3d = features.get("vol_3d_avg", 0.0)
    vol_20d = features.get("vol_20d_avg", 1.0)
    if vol_20d <= 0:
        return False
    rvol = vol_3d / vol_20d
    return rvol <= 0.5


def compute_support_distance(price: float, support: float) -> float:
    if support <= 0:
        return 1.0
    return abs(price - support) / support


def evaluate_structure(features: Dict) -> Dict:
    """
    Final State Machine
    """
    price_signal = compute_price_signal(features)
    flow_signal = compute_flow_signal(features)

    support_distance_pct = compute_support_distance(
        features.get("price", 0.0),
        features.get("support_level", 0.0),
    )

    if price_signal and flow_signal:
        state = StructureState.FORMED
    elif price_signal or flow_signal:
        state = StructureState.FORMING
    else:
        state = StructureState.NOT_FORMED

    watchlist = (
        state == StructureState.FORMING and support_distance_pct <= 0.04
    )

    return {
        "state": state,
        "price_signal": price_signal,
        "flow_signal": flow_signal,
        "support_distance_pct": round(support_distance_pct, 4),
        "watchlist": watchlist,
    }
