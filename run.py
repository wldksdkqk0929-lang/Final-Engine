import sys
import subprocess
import os
import logging
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
    if pip_name is None: pip_name = package
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
    "gate3_dd_pass": 0,  # [Fix] 통계 분리
    "rib_final_pass": 0, # [Fix] 최종 생존
    "start_time": time.time(),
    "end_time": 0
}

# ---------------------------------------------------------
# ⚙️ V11.1 설정 (Robust Engine)
# ---------------------------------------------------------
# [Universe]
TARGET_LIQUID_COUNT = 1200      # 유동성 확보 목표치 (Top 600 + Pool 600)
FINAL_UNIVERSE_SIZE = 800       # 최종 선발

# [Gate 1: Ultra Light] - 5D Data
G1_MIN_PRICE = 5.0
G1_MIN_DOL_VOL = 8_000_000

# [Gate 2: Fast Technical] - 60D Data
G2_MIN_DD_60 = -6.0             # [Fix] -8% -> -6% (완화)
G2_MAX_REC_60 = 0.98            # [Fix] 0.95 -> 0.98 (상승 추세 허용폭 확대)

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
                if 'Test Issue' in df.columns: df = df[df['Test Issue'] == 'N']
                if 'ETF' in df.columns: df = df[df['ETF'] == 'N']
                
                raw_syms = df['Symbol'].dropna().astype(str).tolist()
                valid_pattern = re.compile(r"^[A-Z\.]+$")
                
                for s in raw_syms:
                    s_clean = s.strip().upper()
                    if s_clean in ETF_LIST: continue
                    if valid_pattern.match(s_clean) and len(s_clean) <= 5:
                        symbols.add(s_clean)
        except: continue
    return list(symbols)

def build_initial_universe():
    """
    [Fix] 유동성 상위 1200개가 찰 때까지 계속 스캔하는 루프 구조
    """
    candidates = fetch_us_market_symbols()
    candidates = list(set(candidates + CORE_WATCHLIST))
    
    print_status(f"   📋 Raw Pool: {len(candidates)}개 -> 유동성 타겟 {TARGET_LIQUID_COUNT}개 확보 시작")
    
    scan_pool = list(set(candidates) - set(CORE_WATCHLIST))
    random.shuffle(scan_pool)
    
    # Core는 무조건 포함한다고 가정하고 시작
    liquidity_scores = []
    
    # Core 먼저 처리
    try:
        core_data = yf.download(CORE_WATCHLIST, period="5d", group_by='ticker', threads=True, progress=False)
        for sym in CORE_WATCHLIST:
            try:
                df = core_data[sym] if len(CORE_WATCHLIST) > 1 else core_data
                if not df.empty:
                    avg = (df['Close'] * df['Volume']).mean()
                    liquidity_scores.append((sym, avg))
            except: pass
    except: pass

    # 나머지 Pool 스캔 (목표치 채울 때까지)
    chunk_size = 200
    pool_idx = 0
    
    while len(liquidity_scores) < TARGET_LIQUID_COUNT and pool_idx < len(scan_pool):
        chunk = scan_pool[pool_idx : pool_idx + chunk_size]
        pool_idx += chunk_size
        
        if not chunk: break
        
        try:
            data = yf.download(chunk, period="5d", group_by='ticker', threads=True, progress=False)
            
            # [Fix] MultiIndex 안전 처리
            if isinstance(data.columns, pd.MultiIndex):
                # 데이터가 있는 컬럼만 추출
                valid_cols = set(data.columns.get_level_values(0))
                for sym in chunk:
                    if sym in valid_cols:
                        df = data[sym]
                        if not df.empty:
                            avg = (df['Close'] * df['Volume']).mean()
                            if pd.isna(avg): avg = 0
                            liquidity_scores.append((sym, avg))
            else:
                # 단일 종목 or Empty
                if not data.empty and len(chunk) == 1:
                    avg = (data['Close'] * data['Volume']).mean()
                    liquidity_scores.append((chunk[0], avg))
                    
        except: continue
        
        print(f"   ⚖️ Secured: {len(liquidity_scores)} / {TARGET_LIQUID_COUNT} (Scanned {pool_idx})", end="\r")

    # Ranking & Selection
    liquidity_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Top 600
    top_600 = [x[0] for x in liquidity_scores[:600]]
    
    # Next 600 -> Random 200
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
        batch = universe[i:i+batch_size]
        try:
            data = yf.download(batch, period="5d", group_by='ticker', threads=True, progress=False)
            
            # [Fix] Robust Column Check
            present_tickers = []
            if isinstance(data.columns, pd.MultiIndex):
                present_tickers = set(data.columns.get_level_values(0))
            elif not data.empty:
                present_tickers = batch # Single logic handled implicitly below check
            
            if isinstance(data.columns, pd.MultiIndex):
                for sym in batch:
                    if sym in present_tickers:
                        df = data[sym]
                        if df.empty: continue
                        if df['Close'].mean() >= G1_MIN_PRICE and (df['Close']*df['Volume']).mean() >= G1_MIN_DOL_VOL:
                            survivors.append(sym)
            else:
                if not data.empty and len(batch) == 1:
                    if data['Close'].mean() >= G1_MIN_PRICE and (data['Close']*data['Volume']).mean() >= G1_MIN_DOL_VOL:
                        survivors.append(batch[0])

        except: continue
        
    PIPELINE_STATS["gate1_pass"] = len(survivors)
    print(f"   ➡️ Gate 1 Passed: {len(survivors)}")
    return survivors

def apply_gate_2_fast_tech(universe):
    print_status("🛡️ [Gate 2] Fast Technical (60D)...")
    survivors = []
    batch_size = 100
    
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i+batch_size]
        try:
            data = yf.download(batch, period="60d", group_by='ticker', threads=True, progress=False)
            
            present_tickers = set()
            if isinstance(data.columns, pd.MultiIndex):
                present_tickers = set(data.columns.get_level_values(0))
            
            iter_list = batch if isinstance(data.columns, pd.MultiIndex) else ([batch[0]] if len(batch)==1 else [])

            for sym in iter_list:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if sym not in present_tickers: continue
                        df = data[sym].copy().dropna()
                    else:
                        df = data.copy().dropna()

                    if len(df) < 40: continue
                    
                    high_60 = df['High'].max()
                    cur_price = df['Close'].iloc[-1]
                    
                    if high_60 == 0: continue
                    
                    dd_60 = ((cur_price - high_60) / high_60) * 100
                    rec_ratio = cur_price / high_60
                    
                    # [Fix] Logic relaxed: DD -6% OR Rec <= 0.98
                    if dd_60 <= G2_MIN_DD_60 and rec_ratio <= G2_MAX_REC_60:
                        survivors.append(sym)
                except: continue
        except: continue
        
    PIPELINE_STATS["gate2_pass"] = len(survivors)
    print(f"   ➡️ Gate 2 Passed: {len(survivors)}")
    return survivors

# ==========================================
# 3. RIB V2 (Relaxed Logic)
# ==========================================
def analyze_rib_structure(hist):
    try:
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]
        
        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5: return None
        
        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]
        
        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3: return None
        
        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]
        
        # [Fix] Allow slight undercut (2%) for Base B
        if base_b_price < base_a_price * 0.98: return None 
        if current_price < base_b_price: return None
        
        # Scoring
        score = 0
        # Structure
        ratio = base_b_price / base_a_price
        if 1.03 <= ratio <= 1.15: score += 30
        else: score += 10
        
        # Proximity
        if pivot_price == 0: dist_pct = 99
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        if current_price > pivot_price: score += 25
        elif dist_pct <= 5.0: score += 20
        elif dist_pct <= 15.0: score += 10
        
        # Risk (ATR)
        atr = (recent['High'] - recent['Low']).tail(14).mean()
        if (atr/current_price) < 0.05: score += 20
        
        # Grade
        if current_price > pivot_price: grade = "ACTION"
        elif dist_pct <= 8.0: grade = "SETUP"
        elif dist_pct <= 20.0: grade = "RADAR"
        else: grade = "IGNORE"
        
        return {
            "grade": grade, "rib_score": score, 
            "base_a": base_a_price, "base_b": base_b_price, "pivot": pivot_price,
            "trigger_msg": f"Gap {dist_pct:.1f}%"
        }
    except: return None

def analyze_narrative(symbol):
    return {"narrative_score": 50, "status_label": "Info", "drop_news": [], "recovery_news": []}

# ==========================================
# 4. Final Pipeline (Gate 3 & RIB) - Split Stats
# ==========================================
def apply_gate_3_and_rib(universe):
    print_status("🛡️ [Gate 3 & RIB] Deep Analysis (1Y Data)...")
    survivors = []
    batch_size = 50 
    
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i+batch_size]
        try:
            # [Fix] 1Y Data for Speed
            data = yf.download(batch, period="1y", group_by='ticker', threads=True, progress=False)
            
            present_tickers = set()
            if isinstance(data.columns, pd.MultiIndex):
                present_tickers = set(data.columns.get_level_values(0))
            
            iter_list = batch if isinstance(data.columns, pd.MultiIndex) else ([batch[0]] if len(batch)==1 else [])

            for sym in iter_list:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if sym not in present_tickers: continue
                        df = data[sym].copy().dropna()
                    else:
                        df = data.copy().dropna()
                    
                    if len(df) < 200: continue # 1년치 조금 안되더라도 허용
                    
                    # [Gate 3] Hard Gate (DD252)
                    high_252 = df['High'].max()
                    cur = df['Close'].iloc[-1]
                    dd_252 = ((cur - high_252) / high_252) * 100
                    
                    if dd_252 > G3_MAX_DD_252: continue # 낙폭 부족 탈락
                    
                    # [Stats] Gate 3 DD Passed
                    PIPELINE_STATS["gate3_dd_pass"] += 1
                    
                    # [RIB Analysis]
                    rib_data = analyze_rib_structure(df)
                    if not rib_data: continue
                    if rib_data['rib_score'] < CUTOFF_SCORE: continue
                    
                    # [Stats] Final Passed
                    PIPELINE_STATS["rib_final_pass"] += 1
                    
                    narr = analyze_narrative(sym)
                    
                    survivors.append({
                        "symbol": sym, "price": round(cur, 2), "dd": round(dd_252, 2),
                        "rib_data": rib_data, "narrative": narr
                    })
                except: continue
        except: continue
        print(f"   🧬 Analyzing: {min(i+batch_size, len(universe))}/{len(universe)}", end="\r")
        
    print(f"\n✅ [Pipeline Complete] Final Survivors: {len(survivors)}")
    return survivors

# ==========================================
# 5. Dashboard Generation
# ==========================================
def generate_dashboard(targets):
    action = [s for s in targets if s['rib_data']['grade'] in ['ACTION', 'SETUP']]
    radar = [s for s in targets if s['rib_data']['grade'] == 'RADAR']
    
    def render_card(stock):
        sym = stock['symbol']
        rib = stock['rib_data']
        grade_color = "#e74c3c" if rib['grade'] == 'ACTION' else "#f1c40f"
        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        
        return f"""
        <div class="card">
            <div class="card-header">
                <span class="sym">{sym}</span> <span class="price">${stock['price']}</span>
                <span class="badge" style="background:{grade_color}">{rib['grade']}</span>
                <span class="badge">Score {rib['rib_score']}</span>
            </div>
            <div class="card-body">
                <div class="tv-container" id="{chart_id}" style="height:250px;"></div>
                <script>
                    new TradingView.widget({{
                        "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC", "theme": "dark", "style": "1", "locale": "en", "hide_top_toolbar": true, "hide_legend": true, "container_id": "{chart_id}",
                        "studies": ["MAExp@tv-basicstudies"],
                        "studies_overrides": {{ "MAExp@tv-basicstudies.length": 224, "MAExp@tv-basicstudies.plot.color": "#FFB000", "MAExp@tv-basicstudies.plot.linewidth": 5 }}
                    }});
                </script>
            </div>
        </div>
        """
        
    stats_html = f"""
    <div class="stats-bar">
        <span>Raw: {PIPELINE_STATS['universe_actual']}</span> ➔
        <span>G1: {PIPELINE_STATS['gate1_pass']}</span> ➔
        <span>G2: {PIPELINE_STATS['gate2_pass']}</span> ➔
        <span>G3(DD): {PIPELINE_STATS['gate3_dd_pass']}</span> ➔
        <span style="color:#e67e22; font-weight:bold;">RIB: {len(targets)}</span>
    </div>
    """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>SNIPER V11.1</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <style>
            body {{ background: #131722; color: #ccc; font-family: sans-serif; padding: 20px; }}
            .stats-bar {{ background: #2a2e39; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 20px; font-family: monospace; font-size: 1.1em; }}
            .card {{ background: #1e222d; border: 1px solid #333; border-radius: 8px; margin-bottom: 15px; overflow: hidden; }}
            .card-header {{ padding: 10px; background: #262b3e; display: flex; align-items: center; gap: 10px; }}
            .sym {{ font-size: 1.2em; font-weight: bold; color: #fff; }}
            .badge {{ padding: 3px 6px; border-radius: 4px; font-size: 0.8em; background: #444; color: #fff; }}
        </style>
    </head>
    <body>
        <h1 style="text-align:center; color:#e67e22;">SNIPER V11.1 <span style="font-size:0.6em; color:#777;">ROBUST ENGINE</span></h1>
        {stats_html}
        <h2>🔥 ACTION & SETUP</h2>
        {''.join([render_card(s) for s in action])}
        <h2>📡 RADAR</h2>
        {''.join([render_card(s) for s in radar])}
    </body>
    </html>
    """
    
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

# ==========================================
# 6. Main Execution Block
# ==========================================
if __name__ == "__main__":
    try:
        print_status("🚀 SNIPER V11.1 Robust Engine Start...")
        
        # 1. Universe
        universe = build_initial_universe()
        
        # 2. Gate 1 (Light)
        survivors_g1 = apply_gate_1_light(universe)
        if not survivors_g1: raise Exception("Gate 1 Kill All")
        
        # 3. Gate 2 (Fast Tech)
        survivors_g2 = apply_gate_2_fast_tech(survivors_g1)
        if not survivors_g2: raise Exception("Gate 2 Kill All")
        
        # 4. Gate 3 & RIB (Deep)
        final_targets = apply_gate_3_and_rib(survivors_g2)
        
        # 5. Dashboard
        generate_dashboard(final_targets)
        
        PIPELINE_STATS["end_time"] = time.time()
        duration = PIPELINE_STATS["end_time"] - PIPELINE_STATS["start_time"]
        
        print_status(f"✅ Workflow Complete in {duration:.1f}s")
        print(json.dumps(PIPELINE_STATS, indent=2))
        
    except Exception as e:
        print_status(f"❌ Fatal Error: {e}")
        sys.exit(1)
