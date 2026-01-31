from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

@dataclass(frozen=True)
class ChimeraConfig:
    base_volume_ratio: float = 2.0
    min_volume_ratio: float = 1.2
    step: float = 0.1
    # [Tuned] 20 -> 10 (적절한 집중)
    top_k: int = 10
    use_regime_filter: bool = True
    regime_penalty: float = 0.15
    # [Tuned] 40 -> 35 (타점 정제)
    max_distance_pct: float = 35.0

def _calculate_market_regime(features_list: List[Any]) -> float:
    if not features_list: return 0.0
    rets = [getattr(f, 'ret1d_pct', 0.0) for f in features_list]
    return sum(rets) / len(rets)

def _score(f: Any) -> float:
    vr = float(f.volume_ratio)
    dist = float(f.distance_pct)
    brk = 1.0 if f.breakout_high else 0.0
    # 점수 산식 유지
    dist_term = 1.0 / (1.0 + max(0.0, dist))
    return (vr * 1.0) + (dist_term * 5.0) + (brk * 0.5)

def select_chimera(features_list: List[Any], cfg: Optional[ChimeraConfig] = None) -> List[Dict[str, Any]]:
    cfg = cfg or ChimeraConfig()
    market_temp = _calculate_market_regime(features_list)
    
    penalty = 0.0
    if cfg.use_regime_filter and market_temp < -0.5:
        penalty = cfg.regime_penalty
    
    # Target Hits: Top 10 기준 10%
    universe_size = len(features_list)
    need = max(1, min(cfg.top_k, int((universe_size * 0.10) + 0.99)))

    # [Tuned] Distance 5 ~ 35%
    base = [
        f for f in features_list 
        if f.flow_v1 
        and (5.0 <= f.distance_pct <= cfg.max_distance_pct) 
        and f.breakout_high
    ]
    
    current_min_vol = cfg.min_volume_ratio + penalty
    ratio = cfg.base_volume_ratio + penalty
    best_pool: List[Any] = []

    while ratio + 1e-9 >= current_min_vol:
        pool = [f for f in base if f.volume_ratio >= ratio]
        if len(pool) >= need:
            best_pool = pool
            break
        ratio = round(ratio - cfg.step, 10)
    
    if not best_pool:
        best_pool = [f for f in base if f.volume_ratio >= current_min_vol]

    out = []
    for f in sorted(best_pool, key=_score, reverse=True)[:cfg.top_k]:
        out.append({
            "engine": "Chimera-N", 
            "symbol": f.symbol, 
            "date": f.date.strftime("%Y-%m-%d"),
            "market_temp": round(market_temp, 2),
            "score": round(_score(f), 4),
            "ret1d_pct": round(f.ret1d_pct, 2)
        })
    return out
