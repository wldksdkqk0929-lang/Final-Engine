import os
import json
import time
from datetime import datetime
from engine.metrics import SniperMetrics


class SniperBatchRunner:
    """
    Batch Orchestrator Wrapper
    - processor(symbol) 형태의 callable 주입
    - Core Engine 직접 의존 금지
    """

    def __init__(self, processor, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.processor = processor
        self.base_dir = base_dir
        self.out_dir = os.path.join(base_dir, "data", "out")
        self.metrics = SniperMetrics(base_dir=base_dir)

    # -----------------------------
    # Run Batch
    # -----------------------------

    def run(self, symbols):
        date_str = datetime.now().strftime("%Y-%m-%d")
        day_out_dir = os.path.join(self.out_dir, date_str)
        os.makedirs(day_out_dir, exist_ok=True)

        results = {}

        for symbol in symbols:
            start = time.time()

            try:
                # ---- Core Call ----
                result = self.processor(symbol)

                # ---- Metrics Update ----
                self.metrics.inc("symbol_processed_count")

                if result.get("cache_hit"):
                    self.metrics.inc("cache_hit_count")
                else:
                    self.metrics.inc("cache_miss_count")

                if result.get("api_called"):
                    self.metrics.inc("api_call_count")

                if result.get("blocked"):
                    self.metrics.inc("kill_switch_block_count")

                # ---- Persist Result ----
                out_path = os.path.join(day_out_dir, f"{symbol}.json")
                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, indent=2)

                results[symbol] = result

            except Exception as e:
                # 🔴 Loop Integrity 보장
                self.metrics.inc("error_count")
                results[symbol] = {
                    "symbol": symbol,
                    "status": "error",
                    "error": str(e),
                }
                continue

            finally:
                elapsed = time.time() - start
                self.metrics.record_latency(elapsed)

        metrics_path = self.metrics.write()
        return results, metrics_path
