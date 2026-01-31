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
    
    print("🦁 [Phase-6K] Starting Chimera Engine...")
    
    symbols = load_universe()[:args.max_symbols]
    print(f"📡 Loading Market Data for {len(symbols)} symbols...")
    
    data = {}
    for s in symbols:
        df = load_price_data(s)
        if df is not None: 
            # [CRITICAL FIX] Timezone info removal
            # 데이터의 시간대 정보를 제거하여 단순 날짜 비교가 가능하게 만듦
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            data[s] = df
        
    if not data:
        print("❌ Critical Error: No data loaded. Check 'universe.csv' or internet connection.")
        return

    # 날짜 비교 로직 (이제 에러 없이 작동함)
    all_dates = sorted(list(set().union(*[d.index for d in data.values()])))
    start_ts = pd.Timestamp(args.start)
    all_dates = [d for d in all_dates if d >= start_ts]
    
    trades = []
    rule = RealTradeRule()
    
    print(f"⚔️  Simulating Battle from {args.start} (Real-World Constraints Applied)...")
    for day in all_dates:
        feats = []
        for s in list(data.keys()):
            f = compute_features_for_date(s, data[s], day)
            if f: feats.append(f)
        
        hits = select_chimera(feats)
        for h in hits:
            # 백테스트 함수 호출
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
    
    print("\n" + "="*40)
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
