from engine.engines.engine_intel import SniperV12Intel

class SniperOrchestrator:
    def __init__(self):
        print("[System] Orchestrator Loaded.")
        
        # TODO: thresholds_config는 추후 외부 설정 주입 구조로 개선 가능
        thresholds_config = {}
        self.intel_engine = SniperV12Intel(thresholds_config)

    def run(self):
        print("[System] Pipeline Started.")

        # 테스트 타겟 (Phase 3 실전 진입)
        targets = ["AAPL", "TSLA", "NVDA"]

        print(f"[System] Dispatching Intelligence Engine: {targets}")

        results = {}
        for ticker in targets:
            # 현재는 raw_text mock 구조
            raw_text = f"Mock news text for {ticker}"
            results[ticker] = self.intel_engine.analyze_ticker(
                ticker=ticker,
                raw_text=raw_text,
                current_watch_data=None
            )

        print("\n[System] Intelligence Result Summary")
        for ticker, payload in results.items():
            status = payload["decision"].get("stage")
            reasons = payload["decision"].get("reasons")
            print(f" - {ticker}: {status} | {reasons}")

        print("\n✅ Pipeline Complete.")
