import os
import json
import uuid
import time
from datetime import datetime


class SniperMetrics:
    def __init__(self, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        self.metrics_dir = os.path.join(base_dir, "data", "metrics")
        self.run_id = str(uuid.uuid4())[:8]
        self.start_time = time.time()
        self.date_str = datetime.now().strftime("%Y-%m-%d")

        self.stats = {
            "run_id": self.run_id,
            "date": self.date_str,
            "symbol_processed_count": 0,
            "cache_hit_count": 0,
            "cache_miss_count": 0,
            "api_call_count": 0,
            "kill_switch_block_count": 0,
            "error_count": 0,
            "avg_latency_ms": 0.0,
        }

        self._latencies = []

    # -----------------------------
    # Counters
    # -----------------------------

    def inc(self, key, value=1):
        if key in self.stats:
            self.stats[key] += value

    def record_latency(self, elapsed_sec):
        self._latencies.append(elapsed_sec)

    # -----------------------------
    # Finalize & Persist
    # -----------------------------

    def finalize(self):
        if self._latencies:
            avg = sum(self._latencies) / len(self._latencies)
            self.stats["avg_latency_ms"] = round(avg * 1000, 2)

    def write(self):
        self.finalize()

        day_dir = os.path.join(self.metrics_dir, self.date_str)
        os.makedirs(day_dir, exist_ok=True)

        path = os.path.join(day_dir, f"run_{self.run_id}.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.stats, f, indent=2)

        return path
