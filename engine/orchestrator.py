from engine.engines.engine_intel import IntelEngine


class Orchestrator:
    def __init__(self):
        self.intel_engine = IntelEngine()

    def analyze(self, symbol: str):
        # ⚠️ 절대 이전 상태 전달 금지
        return self.intel_engine.analyze_symbol(symbol)
