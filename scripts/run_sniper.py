from engine.orchestrator import IntelEngine
import logging
from collections import Counter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SNIPER")


def run_sniper_batch(symbols):
    engine = IntelEngine()

    results = []
    for symbol in symbols:
        result = engine.analyze_symbol(symbol)
        results.append(result)

        raw = result.get("raw", {})
        flow_v2 = raw.get("flow_v2", False)
        actionable = (result["structure"] == "FORMED") and flow_v2

        logger.info(
            f"[{symbol}] "
            f"Status={result['structure']} | "
            f"Price={result['price_ok']} | "
            f"Flow_v1={result['flow_ok']} | "
            f"Flow_v2={flow_v2} | "
            f"Actionable={actionable} | "
            f"Dist={result['support_distance_pct']}"
        )

    # ===== 📊 DAILY SNIPER REPORT =====
    structures = Counter(r["structure"] for r in results)

    formed = [r for r in results if r["structure"] == "FORMED"]
    actionable = [
        r for r in formed if r.get("raw", {}).get("flow_v2") is True
    ]

    print("\n" + "=" * 50)
    print("📡 DAILY SNIPER STATUS REPORT")
    print("=" * 50)
    print(f"TOTAL SYMBOLS     : {len(results)}")
    print(f"FORMED            : {structures.get('FORMED', 0)}")
    print(f"FORMING           : {structures.get('FORMING', 0)}")
    print(f"NOT_FORMED        : {structures.get('NOT_FORMED', 0)}")
    print("-" * 50)
    print(f"ACTIONABLE COUNT  : {len(actionable)}")

    if actionable:
        print("🎯 ACTIONABLE SYMBOLS:")
        for r in actionable:
            print(
                f" - {r['symbol']} "
                f"(Dist={r['support_distance_pct']})"
            )
    else:
        print("⏳ No actionable signals today.")

    print("=" * 50 + "\n")

    return results
