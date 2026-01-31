#!/usr/bin/env python3

import logging
from scripts.run_sniper import run_sniper_batch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SNIPER")

def main():
    symbols = [
        "AAPL", "MSFT", "NVDA", "AMZN", "META",
        "TSLA", "AMD", "AVGO", "GOOGL",
        "JPM", "BAC",
        "XOM", "CVX",
        "UNH", "LLY",
        "COST", "WMT"
    ]

    logger.info(f"🚀 Phase-6B Structure Engine | Symbols={len(symbols)}")

    run_sniper_batch(symbols)

if __name__ == "__main__":
    main()
