from engine.batch_runner import SniperBatchRunner


# -----------------------
# Mock Processor
# -----------------------

class MockProcessor:
    def __init__(self):
        self.called = {}

    def __call__(self, symbol):
        count = self.called.get(symbol, 0)
        self.called[symbol] = count + 1

        # First call = API
        if count == 0:
            return {
                "symbol": symbol,
                "cache_hit": False,
                "api_called": True,
                "blocked": False,
            }

        # Second call = Cache HIT
        return {
            "symbol": symbol,
            "cache_hit": True,
            "api_called": False,
            "blocked": False,
        }


def test_phase3_batch_basic():
    processor = MockProcessor()
    runner = SniperBatchRunner(processor)

    symbols = ["AAPL", "AAPL"]
    results, metrics_path = runner.run(symbols)

    assert "AAPL" in results
    assert metrics_path is not None
