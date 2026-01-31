from __future__ import annotations
import time
from typing import Dict, Any
from .base import BaseAnalysisProvider


class MockProvider(BaseAnalysisProvider):
    def __init__(self):
        self.call_count = 0
        self.error_count = 0
        self.total_latency_ms = 0.0

    def health_check(self) -> bool:
        return True

    def analyze_symbol(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        start = time.time()
        try:
            self.call_count += 1
            return {
                "symbol": symbol,
                "status": "MOCK_OK",
                "provider_mode": "MOCK",
                "api_called": False,
                "cache_hit": False,
                "blocked": False,
                "detail": {
                    "note": "mock provider response",
                    "input_keys": sorted(list(data.keys())) if isinstance(data, dict) else [],
                },
            }
        except Exception as e:
            self.error_count += 1
            return {
                "symbol": symbol,
                "status": "MOCK_ERROR",
                "provider_mode": "MOCK",
                "api_called": False,
                "cache_hit": False,
                "blocked": False,
                "error": str(e),
            }
        finally:
            self.total_latency_ms += (time.time() - start) * 1000.0

    def get_usage_stats(self) -> Dict[str, Any]:
        avg = (self.total_latency_ms / self.call_count) if self.call_count else 0.0
        return {
            "total_calls": self.call_count,
            "total_errors": self.error_count,
            "avg_latency_ms": round(avg, 2),
            "estimated_cost_usd": 0.0,
        }
