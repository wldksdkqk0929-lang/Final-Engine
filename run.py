import sys
import subprocess
import os
import json
import random
import time
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import StringIO

# ==========================================
# 0. 시스템 설정 & 라이브러리
# ==========================================
def print_status(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def install_and_import(package, pip_name=None):
    if pip_name is None:
        pip_name = package
    try:
        return __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return __import__(package)

# 필수 라이브러리
yf = install_and_import("yfinance")
requests = install_and_import("requests")
pd = install_and_import("pandas")
np = install_and_import("numpy")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
    from deep_translator import GoogleTranslator

# 전역 설정
TRANSLATION_CACHE = {}
PIPELINE_STATS = {
    "universe_target": 800,
    "universe_actual": 0,
    "gate1_pass": 0,
    "gate2_pass": 0,
    "gate3_dd_pass": 0,   # 통계 분리
    "rib_final_pass": 0,  # 최종 생존
    "start_time": time.time(),
    "end_time": 0
}

# ---------------------------------------------------------
# ⚙️ V11.2 설정 (Robust Engine + Gate2 OR Fix)
# ---------------------------------------------------------
# [Universe]
TARGET_LIQUID_COUNT = 1200      # 유동성 확보 목표치 (Top 600 + Pool 600)
FINAL_UNIVERSE_SIZE = 800       # 최종 선발 (참고)

# [Gate 1: Ultra Light] - 5D Data
G1_MIN_PRICE = 5.0
G1_MIN_DOL_VOL = 8_000_000

# [Gate 2: Fast Technical] - 60D Data
G2_MIN_DD_60 = -6.0             # -8% -> -6% (완화)
G2_MAX_REC_60 = 0.98            # 0.95 -> 0.98 (상승 추세 허용폭 확대)
# Gate2 핵심: (DD 조건) OR (Rec 조건)  -> 아래 로직에서 OR 적용

# [Gate 3: Hard Gate] - 1Y Data (Time Optimized)
G3_MAX_DD_252 = -12.0
CUTOFF_SCORE = 40
# ---------------------------------------------------------

ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD", "UVXY", "SPY", "QQQ", "IWM"]
CORE_WATCHLIST = [
    "DKNG", "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "ROKU", "SQ",
    "COIN", "MSTR", "CVNA", "U", "RBLX", "PATH", "AI", "IONQ", "HIMS"
]

# ==========================================
# 1. Universe Builder (Loop Fix)
# ==========================================
def fetch_us_market_symbols():
    symbols = set()
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
    ]
    print_status("🌐 [Phase 1] 미국 전체 종목 수집 중...")

    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                df = pd.read_csv(StringIO(resp.text), sep="|")
                if 'Test Issue' in df.columns:
                    df = df[df['Test Issue'] == 'N']
                if 'ETF' in df.columns:
                    df = df[df['ETF'] == 'N']

                raw_syms = df['Symbol'].dropna().astype(str).tolist()
                valid_pattern = re.compile(r"^[A-Z\.]+$")

                for s in raw_syms:
                    s_clean = s.strip().upper()
                    if s_clean in ETF_LIST:
                        continue
                    if valid_pattern.match(s_clean) and len(s_clean) <= 5:
                        symbols.add(s_clean)
        except:
            continue

    return list(symbols)

def build_initial_universe():
    """
    유동성 상위 1200개가 찰 때까지 계속 스캔하는 루프 구조
    """
    candidates = fetch_us_market_symbols()
    candidates = list(set(candidates + CORE_WATCHLIST))

    print_status(f"   📋 Raw Pool: {len(candidates)}개 -> 유동성 타겟 {TARGET_LIQUID_COUNT}개 확보 시작")

    scan_pool = list(set(candidates) - set(CORE_WATCHLIST))
    random.shuffle(scan_pool)

    liquidity_scores = []

    # Core 먼저 처리
    try:
        core_data = yf.download(CORE_WATCHLIST, period="5d", group_by='ticker', threads=True, progress=False)
        if isinstance(core_data.columns, pd.MultiIndex):
            present = set(core_data.columns.get_level_values(0))
            for sym in CORE_WATCHLIST:
                if sym not in present:
                    continue
                df = core_data[sym]
                if df is None or df.empty:
                    continue
                avg = (df['Close'] * df['Volume']).mean()
                if pd.isna(avg):
                    avg = 0
                liquidity_scores.append((sym, avg))
        else:
            # 단일/비정상 케이스 (거의 없음)
            if not core_data.empty and len(CORE_WATCHLIST) == 1:
                avg = (core_data['Close'] * core_data['Volume']).mean()
                if pd.isna(avg):
                    avg = 0
                liquidity_scores.append((CORE_WATCHLIST[0], avg))
    except:
        pass

    # 나머지 Pool 스캔 (목표치 채울 때까지)
    chunk_size = 200
    pool_idx = 0

    while len(liquidity_scores) < TARGET_LIQUID_COUNT and pool_idx < len(scan_pool):
        chunk = scan_pool[pool_idx: pool_idx + chunk_size]
        pool_idx += chunk_size
        if not chunk:
            break

        try:
            data = yf.download(chunk, period="5d", group_by='ticker', threads=True, progress=False)

            if isinstance(data.columns, pd.MultiIndex):
                valid_cols = set(data.columns.get_level_values(0))
                for sym in chunk:
                    if sym not in valid_cols:
                        continue
                    df = data[sym]
                    if df is None or df.empty:
                        continue
                    avg = (df['Close'] * df['Volume']).mean()
                    if pd.isna(avg):
                        avg = 0
                    liquidity_scores.append((sym, avg))
            else:
                # 단일 종목
                if not data.empty and len(chunk) == 1:
                    avg = (data['Close'] * data['Volume']).mean()
                    if pd.isna(avg):
                        avg = 0
                    liquidity_scores.append((chunk[0], avg))

        except:
            continue

        print(f"   ⚖️ Secured: {len(liquidity_scores)} / {TARGET_LIQUID_COUNT} (Scanned {pool_idx})", end="\r")

    # Ranking & Selection
    liquidity_scores.sort(key=lambda x: x[1], reverse=True)

    top_600 = [x[0] for x in liquidity_scores[:600]]
    next_pool = [x[0] for x in liquidity_scores[600:1200]]

    if len(next_pool) > 200:
        random_200 = random.sample(next_pool, 200)
    else:
        random_200 = next_pool

    final_universe = list(set(top_600 + random_200 + CORE_WATCHLIST))
    PIPELINE_STATS["universe_actual"] = len(final_universe)

    print(f"\n✅ [Phase 1 Complete] Universe 확정: {len(final_universe)}개 (목표: {FINAL_UNIVERSE_SIZE})")
    return final_universe

# ==========================================
# 2. Gate Engines
# ==========================================
def apply_gate_1_light(universe):
    print_status("🛡️ [Gate 1] Price/Vol Check (5D)...")
    survivors = []
    batch_size = 100

    for i in range(0, len(universe), batch_size):
        batch = universe[i:i + batch_size]
        try:
            data = yf.download(batch, period="5d", group_by='ticker', threads=True, progress=False)

            if isinstance(data.columns, pd.MultiIndex):
                present = set(data.columns.get_level_values(0))
                for sym in batch:
                    if sym not in present:
                        continue
                    df = data[sym]
                    if df is None or df.empty:
                        continue
                    avg_close = df['Close'].mean()
                    avg_dol_vol = (df['Close'] * df['Volume']).mean()
                    if avg_close >= G1_MIN_PRICE and avg_dol_vol >= G1_MIN_DOL_VOL:
                        survivors.append(sym)
            else:
                # 단일
                if not data.empty and len(batch) == 1:
                    avg_close = data['Close'].mean()
                    avg_dol_vol = (data['Close'] * data['Volume']).mean()
                    if avg_close >= G1_MIN_PRICE and avg_dol_vol >= G1_MIN_DOL_VOL:
                        survivors.append(batch[0])
        except:
            continue

    PIPELINE_STATS["gate1_pass"] = len(survivors)
    print(f"   ➡️ Gate 1 Passed: {len(survivors)}")
    return survivors

def apply_gate_2_fast_tech(universe):
    """
    Gate 2 핵심: DD -6% OR Rec <= 0.98  (OR 적용)
    """
    print_status("🛡️ [Gate 2] Fast Technical (60D)...")
    survivors = []
    batch_size = 100

    for i in range(0, len(universe), batch_size):
        batch = universe[i:i + batch_size]
        try:
            data = yf.download(batch, period="60d", group_by='ticker', threads=True, progress=False)

            present = set()
            if isinstance(data.columns, pd.MultiIndex):
                present = set(data.columns.get_level_values(0))
                iter_list = batch
            else:
                iter_list = [batch[0]] if len(batch) == 1 and not data.empty else []

            for sym in iter_list:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if sym not in present:
                            continue
                        df = data[sym].copy().dropna()
                    else:
                        df = data.copy().dropna()

                    if df is None or len(df) < 40:
                        continue

                    high_60 = df['High'].max()
                    cur_price = df['Close'].iloc[-1]
                    if high_60 <= 0:
                        continue

                    dd_60 = ((cur_price - high_60) / high_60) * 100
                    rec_ratio = cur_price / high_60

                    # ✅ OR FIX
                    if (dd_60 <= G2_MIN_DD_60) or (rec_ratio <= G2_MAX_REC_60):
                        survivors.append(sym)
                except:
                    continue
        except:
            continue

    PIPELINE_STATS["gate2_pass"] = len(survivors)
    print(f"   ➡️ Gate 2 Passed: {len(survivors)}")
    return survivors

# ==========================================
# 3. RIB V2 (Relaxed Logic)
# ==========================================
def analyze_rib_structure(hist):
    try:
        recent = hist.tail(120).copy()
        if recent is None or recent.empty or len(recent) < 60:
            return None

        current_price = recent["Close"].iloc[-1]
        if current_price <= 0:
            return None

        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]

        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5:
            return None

        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]

        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3:
            return None

        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]

        # Allow slight undercut (2%) for Base B
        if base_b_price < base_a_price * 0.98:
            return None
        if current_price < base_b_price:
            return None

        # Scoring
        score = 0

        # Structure
        ratio = base_b_price / base_a_price if base_a_price > 0 else 0
        if 1.03 <= ratio <= 1.15:
            score += 30
        else:
            score += 10

        # Proximity
        if pivot_price <= 0:
            dist_pct = 99
        else:
            dist_pct = (pivot_price - current_price) / pivot_price * 100

        if current_price > pivot_price:
            score += 25
        elif dist_pct <= 5.0:
            score += 20
        elif dist_pct <= 15.0:
            score += 10

        # Risk (ATR)
        atr = (recent['High'] - recent['Low']).tail(14).mean()
        if pd.isna(atr):
            atr = 0
        if (atr / current_price) < 0.05:
            score += 20

        # Grade
        if current_price > pivot_price:
            grade = "ACTION"
        elif dist_pct <= 8.0:
            grade = "SETUP"
        elif dist_pct <= 20.0:
            grade = "RADAR"
        else:
            grade = "IGNORE"

        return {
            "grade": grade,
            "rib_score": int(score),
            "base_a": float(base_a_price),
            "base_b": float(base_b_price),
            "pivot": float(pivot_price),
            "trigger_msg": f"Gap {dist_pct:.1f}%"
        }
    except:
        return None

def analyze_narrative(symbol):
    # (현재 버전은 내러티브를 강하게 쓰지 않기로 했으므로 placeholder 유지)
    return {"narrative_score": 50, "status_label": "Info", "drop_news": [], "recovery_news": []}

# ==========================================
# 4. Final Pipeline (Gate 3 & RIB) - Split Stats
# ==========================================
def apply_gate_3_and_rib(universe):
    print_status("🛡️ [Gate 3 & RIB] Deep Analysis (1Y Data)...")
