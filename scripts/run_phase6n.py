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
    
    print("🦁 [Phase-6N] Final Polish Running...")
    print("   -> Specs: Top-10, Distance < 35%, TP(+8%)")
    
    symbols = load_universe()[:args.max_symbols]
    data = {}
    for s in symbols:
        df = load_price_data(s)
        if df is not None:
            if df.index.tz is not None: df.index = df.index.tz_localize(None)
            data[s] = df
        
    if not data: return

    all_dates = sorted(list(set().union(*[d.index for d in data.values()])))
    all_dates = [d for d in all_dates if d >= pd.Timestamp(args.start)]
    
    trades = []
    rule = RealTradeRule()
    
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
        print("No trades.")
        return

    df_t = pd.DataFrame(trades)
    df_t["net_ret_pct"] = df_t["ret"] * 100
    win_rate = (df_t["net_ret_pct"] > 0).mean() * 100
    total_pnl = df_t["net_ret_pct"].sum()
    
    print("\n" + "="*40)
    print(f"💎 PHASE-6N FINAL REPORT (Precision Tuned)")
    print("="*40)
    print(f"Total Trades : {len(df_t)}")
    print(f"Win Rate     : {win_rate:.2f}%")
    print(f"Total PnL    : {total_pnl:.2f}%")
    print("-" * 40)
    print("Exit Types Breakdown:")
    print(df_t["exit_type"].value_counts())
    print("="*40)

if __name__ == "__main__":
    main()
