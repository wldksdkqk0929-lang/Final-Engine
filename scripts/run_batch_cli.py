import sys
from engine.batch_runner import SniperBatchRunner
from engine.engines.engine_intel import SniperV12Intel


def main():
    print("🔥 [CLI] Starting Sniper Batch Process...")

    # [Target Definition]
    target_symbols = ["AAPL", "TSLA", "NVDA", "MSFT", "PLTR"]

    # [Dependency Injection]
    thresholds_config = {
        "PASS": 80,
        "READY": 60,
        "FAIL": 0
    }

    processor = SniperV12Intel(thresholds_config=thresholds_config)
    runner = SniperBatchRunner(processor=processor)

    try:
        # 🔴 IMPORTANT: runner returns TUPLE
        stats, _ = runner.run(target_symbols)

        error_count = stats.get("error_count", 0)

        if error_count > 0:
            print(f"⚠️ [CLI] Batch completed with {error_count} errors.")
        else:
            print("✅ [CLI] Batch completed successfully.")

    except Exception as e:
        print(f"❌ [CLI] Critical Batch Failure: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
