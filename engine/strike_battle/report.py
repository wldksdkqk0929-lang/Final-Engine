from __future__ import annotations
from typing import Dict, Any

def print_summary(result: Dict[str, Any]) -> None:
    print("")
    print("=== Battle Summary ===")
    
    loaded = result.get("loaded_symbols", "N/A")
    scanned = result.get("days_scanned", "N/A")
    print(f"loaded_symbols={loaded}  days_scanned={scanned}")
    print("")

    # 결과 딕셔너리 구조가 맞는지 확인 후 출력
    for k in ["D", "C"]:
        if k not in result:
            print(f"[{k}] NO DATA")
            continue
            
        # 디버깅: 키 에러 방지용 안전 접근
        engine_res = result[k]
        if "summary" not in engine_res:
            print(f"[{k}] 'summary' key missing. Raw keys: {list(engine_res.keys())}")
            continue

        s = engine_res["summary"]
        print(
            f"[{k}] trades={s.get('trades',0)}  "
            f"win_rate={s.get('win_rate',0)}%  "
            f"median_ret={s.get('median_ret',0)}%  "
            f"avg_ret={s.get('avg_ret',0)}%  "
            f"total_pnl={s.get('total_pnl',0)}%  "
            f"mdd={s.get('mdd',0)}%  "
            f"big_loss_rate={s.get('big_loss_rate',0)}%"
        )
    print("")

def print_fired_days(result: Dict[str, Any], engine: str) -> None:
    print(f"=== {engine} Fired Days ===")
    if engine not in result:
        print("NONE (engine missing)")
        return
    
    d = result[engine].get("fired_days", {})
    if not d:
        print("NONE (0 days)")
        return

    for day in sorted(d.keys()):
        print(f"{day} | hits={d[day]}")
