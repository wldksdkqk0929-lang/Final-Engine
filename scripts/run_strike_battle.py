from __future__ import annotations
import argparse
import json
import pandas as pd
import sys
import os

# 모듈 경로 확보
sys.path.append(os.getcwd())

from engine.strike_battle.universe import load_universe
from engine.strike_battle.backtest import run_battle, TradeRule
from engine.strike_battle.engine_d import DConfig
from engine.strike_battle.engine_c import CConfig
from engine.strike_battle.report import print_summary, print_fired_days

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default=None)
    p.add_argument("--end", default=None)
    p.add_argument("--max_symbols", type=int, default=50)
    
    # C안 파라미터 (유동적 타겟 히트)
    p.add_argument("--c_min_vol", type=float, default=1.2)
    p.add_argument("--c_start_vol", type=float, default=2.0)
    p.add_argument("--c_step", type=float, default=0.1)
    
    args = p.parse_args()

    # 유니버스 로드
    try:
        symbols = load_universe()
    except Exception:
        # 파일 없을 시 안전장치
        symbols = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL"]
        
    if args.max_symbols:
        symbols = symbols[:args.max_symbols]

    # 설정
    rule = TradeRule(hold_days=10)
    d_cfg = DConfig() # 기본값 사용
    c_cfg = CConfig(
        start_volume_ratio=args.c_start_vol,
        min_volume_ratio=args.c_min_vol,
        step=args.c_step
    )

    # 실행
    result = run_battle(
        symbols=symbols,
        start=args.start,
        end=args.end,
        rule=rule,
        d_cfg=d_cfg,
        c_cfg=c_cfg
    )

    # 디버깅용: 결과 구조가 이상하면 원본 출력
    # print("DEBUG RAW RESULT:", result.keys()) 

    print_summary(result)
    print_fired_days(result, "D")
    print("")
    print_fired_days(result, "C")

if __name__ == "__main__":
    main()
