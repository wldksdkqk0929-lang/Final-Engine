from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import pandas as pd

@dataclass
class RealTradeRule:
    hold_days: int = 10
    stop_loss_pct: float = -7.0     # SL -7% 유지
    tp1_pct: float = 5.0            # [Modified] 8% -> 5% (빠른 회전)
    tp2_pct: float = 20.0           # 대박은 유지
    cost_bps: float = 20.0          # 비용 0.2%

def _calc_real_return(df: pd.DataFrame, signal_date: pd.Timestamp, rule: RealTradeRule) -> Dict[str, Any]:
    idx = df.index.get_loc(signal_date)
    if isinstance(idx, slice): idx = idx.stop - 1
    entry_i = idx + 1
    if entry_i >= len(df): return {"ret": 0.0, "exit_type": "end"}
    
    entry_px = float(df["Open"].iloc[entry_i])
    cost_rate = rule.cost_bps / 10000.0
    
    position_pct = 1.0
    realized_ret = 0.0
    tp1_hit = False
    exit_type = "hold"
    current_sl_pct = rule.stop_loss_pct 

    end_i = min(entry_i + rule.hold_days, len(df))
    for i in range(entry_i, end_i):
        day_low = float(df["Low"].iloc[i])
        day_high = float(df["High"].iloc[i])
        
        # Stop Loss
        loss_pct = (day_low / entry_px - 1.0) * 100
        if loss_pct <= current_sl_pct:
            exit_px = entry_px * (1 + current_sl_pct/100)
            realized_ret += position_pct * (exit_px / entry_px - 1.0)
            position_pct = 0.0
            if exit_type == "hold": exit_type = "stop_loss"
            elif tp1_hit: exit_type = "tp1_then_sl"
            break

        # Take Profit 1 (+5%)
        if not tp1_hit:
            profit_pct = (day_high / entry_px - 1.0) * 100
            if profit_pct >= rule.tp1_pct:
                realized_ret += 0.5 * (rule.tp1_pct / 100.0)
                position_pct = 0.5
                tp1_hit = True
                exit_type = "tp1_hold"
                current_sl_pct = 0.0 

        # Take Profit 2 (+20%)
        if tp1_hit or (not tp1_hit):
            profit_pct = (day_high / entry_px - 1.0) * 100
            if profit_pct >= rule.tp2_pct:
                realized_ret += position_pct * (rule.tp2_pct / 100.0)
                position_pct = 0.0
                exit_type = "tp_max"
                break
    
    if position_pct > 0.0:
        final_close = float(df["Close"].iloc[end_i - 1])
        realized_ret += position_pct * (final_close / entry_px - 1.0)
        
    net_ret = realized_ret - cost_rate
    return {"ret": net_ret, "exit_type": exit_type}
