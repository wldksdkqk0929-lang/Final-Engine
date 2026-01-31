import os
import csv
from typing import List

def load_universe() -> List[str]:
    candidates = ["universe.csv", "data/universe.csv"]
    env_path = os.getenv("STRIKE_UNIVERSE_CSV", "").strip()
    if env_path: candidates.insert(0, env_path)
    
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    syms = [row[0].strip().upper() for row in reader if row and row[0].strip()]
                    return list(dict.fromkeys(syms))
            except: pass
    return ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL"]