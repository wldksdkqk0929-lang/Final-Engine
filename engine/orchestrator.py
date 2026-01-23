from engine.engines.engine_intel import EngineIntel

class SniperOrchestrator:
    def __init__(self):
        print("[System] Orchestrator Loaded.")
        self.intel_engine = EngineIntel()

    def run(self):
        print("[System] Pipeline Started.")

        # 테스트 타겟 (Phase 3 실전 진입)
        targets = ["AAPL", "TSLA", "NVDA"]

        print(f"[System] Dispatching Intelligence Engine: {targets}")

        results = self.intel_engine.run(targets)

        print("\n[System] Intelligence Result Summary")
        for ticker, payload in results.items():
            status = payload["analysis"].get("status")
            catalyst = payload["analysis"].get("catalyst")
            print(f" - {ticker}: {status} | {catalyst}")

        print("\n✅ Pipeline Complete.")
