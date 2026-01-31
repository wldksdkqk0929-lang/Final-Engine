import os

# 1. 디렉토리 생성
dirs = ["engine/strike_battle", "scripts"]
for d in dirs:
    os.makedirs(d, exist_ok=True)

# 2. 파일 내용 정의
files = {}

# [A] __init__.py
files["engine/strike_battle/__init__.py"] = ""

# [B] universe.py
files["engine/strike_battle/universe.py"] = """
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
"""

# [C] data_loader.py
files["engine/strike_battle/data_loader.py"] = """
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import yfinance as yf

@dataclass
class LoadConfig:
    lookback_days: int = 365
    auto_adjust: bool = True

def load_price_data(symbol: str, cfg: Optional[LoadConfig] = None) -> Optional[pd.DataFrame]:
    if cfg is None: cfg = LoadConfig()
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="2y", interval="1d", auto_adjust=cfg.auto_adjust)
        if df.empty: return None
        return df
    except Exception:
        return None
"""

# [D] indicators.py
files["engine/strike_battle/indicators.py"] = """
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd

@dataclass
class Features:
    symbol: str
    date: pd.Timestamp
    close: float
    high: float
    low: float
    volume: float
    volume_ratio: float
    distance_pct: float
    ret1d_pct: float
    flow_v1: bool
    breakout_high: bool

def compute_features_for_date(symbol: str, df: pd.DataFrame, date: pd.Timestamp) -> Optional[Features]:
    if date not in df.index: return None
    idx = df.index.get_loc(date)
    if isinstance(idx, slice): idx = idx.stop - 1
    if idx < 60: return None 

    sub = df.iloc[:idx+1]
    
    close = float(sub["Close"].iloc[-1])
    high = float(sub["High"].iloc[-1])
    low = float(sub["Low"].iloc[-1])
    vol = float(sub["Volume"].iloc[-1])
    
    vol_avg = sub["Volume"].iloc[-11:-1].mean()
    vol_ratio = vol / vol_avg if vol_avg > 0 else 0.0
    
    low_60 = sub["Low"].iloc[-61:].min()
    dist_pct = (close - low_60) / low_60 * 100 if low_60 > 0 else 999.0
    
    ma5 = sub["Close"].iloc[-5:].mean()
    ma20 = sub["Close"].iloc[-20:].mean()
    flow = ma5 > ma20
    
    prev_high = sub["High"].iloc[-6:-1].max()
    breakout = high > prev_high
    
    if len(sub) > 1:
        prev_close = sub["Close"].iloc[-2]
        ret = (close / prev_close - 1.0) * 100 if prev_close > 0 else 0.0
    else:
        ret = 0.0

    return Features(symbol, date, close, high, low, vol, vol_ratio, dist_pct, ret, flow, breakout)
"""

# [E] engine_chimera.py
files["engine/strike_battle/engine_chimera.py"] = """
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

@dataclass(frozen=True)
class ChimeraConfig:
    base_volume_ratio: float = 2.0
    min_volume_ratio: float = 1.2
    step: float = 0.1
    top_k: int = 20
    use_regime_filter: bool = True
    regime_penalty: float = 0.3

def _calculate_market_regime(features_list: List[Any]) -> float:
    if not features_list: return 0.0
    rets = [getattr(f, 'ret1d_pct', 0.0) for f in features_list]
    return sum(rets) / len(rets)

def _score(f: Any) -> float:
    vr = float(f.volume_ratio)
    dist = float(f.distance_pct)
    brk = 1.0 if f.breakout_high else 0.0
    dist_term = 1.0 / (1.0 + max(0.0, dist))
    return (vr * 1.0) + (dist_term * 5.0) + (brk * 0.5)

def select_chimera(features_list: List[Any], cfg: Optional[ChimeraConfig] = None) -> List[Dict[str, Any]]:
    cfg = cfg or ChimeraConfig()
    market_temp = _calculate_market_regime(features_list)
    
    penalty = 0.0
    if cfg.use_regime_filter and market_temp < -0.5:
        penalty = cfg.regime_penalty
    
    universe_size = len(features_list)
    need = max(1, min(5, int((universe_size * 0.10) + 0.99)))

    base = [f for f in features_list if f.flow_v1 and (5.0 <= f.distance_pct <= 40.0) and f.breakout_high]
    
    current_min_vol = cfg.min_volume_ratio + penalty
    ratio = cfg.base_volume_ratio + penalty
    best_pool: List[Any] = []

    while ratio + 1e-9 >= current_min_vol:
        pool = [f for f in base if f.volume_ratio >= ratio]
        if len(pool) >= need:
            best_pool = pool
            break
        ratio = round(ratio - cfg.step, 10)
    
    if not best_pool:
        best_pool = [f for f in base if f.volume_ratio >= current_min_vol]

    out = []
    for f in sorted(best_pool, key=_score, reverse=True)[:cfg.top_k]:
        out.append({
            "engine": "Chimera", 
            "symbol": f.symbol, 
            "date": f.date.strftime("%Y-%m-%d"),
            "market_temp": round(market_temp, 2),
            "penalty_applied": penalty > 0,
            "score": round(_score(f), 4),
            "ret1d_pct": round(f.ret1d_pct, 2)
        })
    return out
"""

# [F] backtest_chimera.py
files["engine/strike_battle/backtest_chimera.py"] = """
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import pandas as pd

@dataclass
class RealTradeRule:
    hold_days: int = 10
    stop_loss_pct: float = -5.0
    take_profit_pct: float = 15.0
    cost_bps: float = 20.0

def _calc_real_return(df: pd.DataFrame, signal_date: pd.Timestamp, rule: RealTradeRule) -> Dict[str, Any]:
    idx = df.index.get_loc(signal_date)
    if isinstance(idx, slice): idx = idx.stop - 1
    entry_i = idx + 1
    if entry_i >= len(df): return {"ret": 0.0, "exit_type": "end"}
    
    entry_px = float(df["Open"].iloc[entry_i])
    cost = rule.cost_bps / 10000.0
    
    exit_i = min(entry_i + rule.hold_days - 1, len(df)-1)
    exit_px = float(df["Close"].iloc[exit_i])
    exit_type = "hold"
    
    for i in range(entry_i, min(entry_i + rule.hold_days, len(df))):
        day_low = float(df["Low"].iloc[i])
        day_high = float(df["High"].iloc[i])
        
        if (day_low / entry_px - 1.0) * 100 <= rule.stop_loss_pct:
            exit_px = entry_px * (1 + rule.stop_loss_pct/100)
            exit_type = "stop_loss"
            break
            
        if (day_high / entry_px - 1.0) * 100 >= rule.take_profit_pct:
            exit_px = entry_px * (1 + rule.take_profit_pct/100)
            exit_type = "take_profit"
            break
            
    net_ret = (exit_px / entry_px - 1.0) - cost
    return {"ret": net_ret, "exit_type": exit_type}
"""

# [G] run_phase6k.py
files["scripts/run_phase6k.py"] = """
from __future__ import annotations
import argparse
import pandas as pd
import sys
import os

sys.path.append(os.getcwd())

from engine.strike_battle.universe import load_universe
from engine.strike_battle.data_loader import load_price_data
from engine.strike_battle.indicators import compute_features_for_date
from engine.strike_battle.engine_chimera import select_chimera
from engine.strike_battle.backtest_chimera import _calc_real_return, RealTradeRule

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2025-06-01")
    p.add_argument("--max_symbols", type=int, default=50)
    args = p.parse_args()
    
    print("🦁 [Phase-6K] Starting Chimera Engine Installation Check...")
    
    symbols = load_universe()[:args.max_symbols]
    print(f"📡 Loading Market Data for {len(symbols)} symbols...")
    
    data = {}
    for s in symbols:
        df = load_price_data(s)
        if df is not None: data[s] = df
        
    if not data:
        print("❌ Critical Error: No data loaded. Check 'universe.csv' or internet connection.")
        return

    all_dates = sorted(list(set().union(*[d.index for d in data.values()])))
    all_dates = [d for d in all_dates if d >= pd.Timestamp(args.start)]
    
    trades = []
    rule = RealTradeRule()
    
    print("⚔️  Simulating Battle (Real-World Constraints Applied)...")
    for day in all_dates:
        feats = []
        for s in list(data.keys()):
            f = compute_features_for_date(s, data[s], day)
            if f: feats.append(f)
        
        hits = select_chimera(feats)
        for h in hits:
            res = _calc_real_return(data[h["symbol"]], pd.Timestamp(h["date"]), rule)
            h.update(res)
            trades.append(h)
            
    if not trades:
        print("⚠️  No trades generated in this period.")
        return

    df_t = pd.DataFrame(trades)
    df_t["net_ret_pct"] = df_t["ret"] * 100
    win_rate = (df_t["net_ret_pct"] > 0).mean() * 100
    total_pnl = df_t["net_ret_pct"].sum()
    
    print("\\n" + "="*40)
    print(f"🦁 PHASE-6K CHIMERA FINAL REPORT")
    print("="*40)
    print(f"Total Trades : {len(df_t)}")
    print(f"Win Rate     : {win_rate:.2f}%")
    print(f"Total PnL    : {total_pnl:.2f}% (Fees & Slippage Applied)")
    print("-" * 40)
    print("Exit Types Breakdown:")
    print(df_t["exit_type"].value_counts())
    print("="*40)

if __name__ == "__main__":
    main()
"""

# 3. 파일 쓰기
print("🛠️ Installing Phase-6K Chimera Engine...")
for path, content in files.items():
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip())
    print(f"   -> Created: {path}")

print("✅ Installation Complete. You can now run the simulation.")
