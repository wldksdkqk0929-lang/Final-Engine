import sys
import subprocess
import os
import logging
import json
import random
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import StringIO

# ==========================================
# 0. 실행 엔트리 포인트 확인을 위한 로그 설정
# ==========================================
# (이 부분이 없으면 GitHub Actions에서 아무것도 안 찍힙니다)
def print_system_status(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

# ==========================================
# 1. 라이브러리 및 환경 설정
# ==========================================
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

# ---------------------------------------------------------
# ⚙️ 필터 설정 (V9.3 Adaptive + RIB V2 Score)
# ---------------------------------------------------------
UNIVERSE_MAX = 150
CUTOFF_SCORE = 70       # RIB Score (0~100) 기준
CUTOFF_STRUCT = 1.05    # Base B >= Base A * 1.05
CUTOFF_NOISE = 2        # Noise Score limit
CUTOFF_VOL_RATIO = 0.06 # ATR/Price ratio limit
CUTOFF_DEEP_DROP = -55  # Max Drawdown limit
# ---------------------------------------------------------

ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]
CORE_WATCHLIST = [
    "DKNG", "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "ROKU", "SQ",
    "COIN", "MSTR", "CVNA", "U", "RBLX", "PATH", "AI", "IONQ", "HIMS"
]

# ==========================================
# 2. Universe Builder
# ==========================================
def fetch_nasdaq_symbols():
    symbols = set()
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
    ]
    
    print_system_status("🌐 [Universe] 거래소 리스트 다운로드 중...")
    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                df = pd.read_csv(StringIO(resp.text), sep="|")
                if 'Test Issue' in df.columns: df = df[df['Test Issue'] == 'N']
                if 'ETF' in df.columns: df = df[df['ETF'] == 'N']
                clean_syms = df['Symbol'].dropna().astype(str).tolist()
                for s in clean_syms:
                    if s.isalpha() and len(s) <= 4: symbols.add(s)
        except Exception as e:
            print(f"⚠️ [Universe] 리스트 다운로드 실패 ({url}): {e}")
            continue
    return list(symbols)

def build_universe():
    print_system_status("🏗️ [Universe Builder] 유니버스 구축 시작...")
    candidates = fetch_nasdaq_symbols()
    
    if len(candidates) < 10:
        print("⚠️ [Universe] 온라인 수집 실패. 기본 리스트 사용.")
        candidates = list(set(CORE_WATCHLIST + ["AAPL", "MSFT", "TSLA", "NVDA", "AMD"]))
    else:
        candidates = list(set(candidates + CORE_WATCHLIST))

    print(f"   📋 1차 후보군: {len(candidates)}개 심볼")
    print(f"   ⚖️ 유동성 분석 중 (Target: Top {UNIVERSE_MAX})...")
    
    final_universe = []
    chunk_size = 500
    liquidity_scores = []

    scan_pool = list(set(candidates) - set(CORE_WATCHLIST))
    random.shuffle(scan_pool)
    scan_targets = CORE_WATCHLIST + scan_pool[:1000]

    for i in range(0, len(scan_targets), chunk_size):
        chunk = scan_targets[i:i+chunk_size]
        try:
            data = yf.download(chunk, period="5d", progress=False, group_by='ticker', threads=True)
            for sym in chunk:
                try:
                    if len(chunk) == 1: df = data
                    else: df = data[sym]
                    if df.empty: continue
                    avg_dol_vol = (df['Close'] * df['Volume']).mean()
                    if pd.isna(avg_dol_vol): avg_dol_vol = 0
                    liquidity_scores.append((sym, avg_dol_vol))
                except: continue
        except Exception as e:
            continue
        print(f"   Running.. {min(i+chunk_size, len(scan_targets))}/{len(scan_targets)} verified", end="\r")

    liquidity_scores.sort(key=lambda x: x[1], reverse=True)
    top_n = liquidity_scores[:UNIVERSE_MAX]
    final_universe = [x[0] for x in top_n]
    
    for core in CORE_WATCHLIST:
        if core not in final_universe: final_universe.append(core)
            
    final_universe = list(set(final_universe))
    print(f"\n✅ [Universe] 최종 확정: {len(final_universe)}개 종목 (Liquidity Top + Core)")
    return final_universe

# ==========================================
# 3. Re-Ignition Engine V2 (Component Scoring)
# ==========================================
def calculate_structure_quality(base_a, base_b, base_a_date, base_b_date):
    try:
        score = 0
        if base_a == 0: return 0
        ratio = base_b / base_a
        
        if 1.03 <= ratio <= 1.15: score += 15
        elif 1.00 < ratio < 1.03: score += 5
        elif ratio > 1.15: score += 7
        else: return 0 

        da = datetime.strptime(base_a_date, "%Y-%m-%d")
        db = datetime.strptime(base_b_date, "%Y-%m-%d")
        days = (db - da).days
        
        if days >= 30: score += 15
        elif days >= 14: score += 10
        elif days >= 7: score += 5
        
        return min(30, score)
    except: return 0

def calculate_compression_energy(hist):
    try:
        score = 0
        if len(hist) < 60: return 10
        recent_window = 10
        past_window = 60
        
        high_low = hist["High"] - hist["Low"]
        atr_recent = high_low.tail(recent_window).mean()
        atr_past = high_low.tail(past_window).mean()
        
        if atr_past == 0: return 0
        atr_ratio = atr_recent / atr_past
        
        if atr_ratio < 0.7: score += 15
        elif atr_ratio < 0.9: score += 10
        elif atr_ratio < 1.1: score += 5
        
        vol_recent = hist["Volume"].tail(recent_window).mean()
        vol_past = hist["Volume"].tail(past_window).mean()
        if vol_past == 0: return 0
        vol_ratio = vol_recent / vol_past
        
        if vol_ratio < 0.7: score += 10
        elif vol_ratio < 0.9: score += 5
        
        return min(25, score)
    except: return 0

def calculate_breakout_proximity(current_price, pivot_price, hist):
    try:
        score = 0
        if pivot_price == 0: return 0
        dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        if current_price > pivot_price: score += 25
        elif 0 <= dist_pct <= 3.0: score += 15
        elif 3.0 < dist_pct <= 8.0: score += 10
        elif dist_pct <= 15.0: score += 5
            
        ma5 = hist["Close"].rolling(5).mean().iloc[-1]
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        if ma5 > ma20: score += 10
        
        return min(25, score)
    except: return 0

def calculate_risk_stability(current_price, hist, noise_score=0):
    try:
        score = 20
        high_low = hist["High"] - hist["Low"]
        atr = high_low.tail(20).mean()
        vol_ratio = atr / current_price if current_price > 0 else 0
        
        if vol_ratio > 0.05: score -= 5
        if vol_ratio > 0.08: score -= 5
        score -= (noise_score * 5)
        
        return max(0, score)
    except: return 0

def analyze_reignition_structure(hist, noise_score=0):
    try:
        if len(hist) < 120: return None
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
        # Base A
        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]
        base_a_date = base_a_idx.strftime("%Y-%m-%d")
        
        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5: 
            return {"status": "FORMING_A", "rib_score": 0, "grade": "IGNORE", "priority": 4}

        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]
        pivot_date = pivot_idx.strftime("%Y-%m-%d")
        
        if pivot_date == base_a_date:
             return {"status": "BOUNCING", "rib_score": 10, "grade": "IGNORE", "priority": 4}

        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3: 
             return {"status": "AT_PIVOT", "rib_score": 20, "grade": "IGNORE", "priority": 4}

        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]
        base_b_date = base_b_idx.strftime("%Y-%m-%d")

        # Kill Switch
        if base_b_price < base_a_price:
            return {"status": "INVALID (Low Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}
        if current_price < base_b_price:
            return {"status": "INVALID (B Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}

        # V2 Scoring
        s_struct = calculate_structure_quality(base_a_price, base_b_price, base_a_date, base_b_date)
        s_comp = calculate_compression_energy(hist)
        s_prox = calculate_breakout_proximity(current_price, pivot_price, hist)
        s_risk = calculate_risk_stability(current_price, hist, noise_score)
        
        total_score = s_struct + s_comp + s_prox + s_risk
        
        # Grading
        if pivot_price == 0: dist_pct = 0
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        status = ""
        grade = "IGNORE"
        priority = 4
        trigger_msg = ""
        badge_color = "#95a5a6"

        if current_price > pivot_price:
            status = "🔥 RIB BREAKOUT"
            grade = "ACTION"
            priority = 1
            trigger_msg = "Pivot 돌파 확인. 모멘텀 발생."
            badge_color = "#e74c3c"
        elif dist_pct <= 3.0:
            status = "🚀 RIB READY"
            grade = "SETUP"
            priority = 2
            trigger_msg = f"돌파 임박 ({dist_pct:.1f}%). 응축도 확인."
            badge_color = "#e67e22"
        elif dist_pct <= 10.0:
            status = "👀 RIB WATCH"
            grade = "RADAR"
            priority = 3
            trigger_msg = f"구조 형성 중 ({dist_pct:.1f}%)."
            badge_color = "#f1c40f"
        else:
            status = "💤 RIB EARLY"
            grade = "IGNORE"
            priority = 4
            trigger_msg = "이격도 큼."

        return {
            "base_a": base_a_price, "base_a_date": base_a_date,
            "pivot": pivot_price, "pivot_date": pivot_date,
            "base_b": base_b_price, "base_b_date": base_b_date,
            "distance": dist_pct,
            "status": status,
            "grade": grade,
            "priority": priority,
            "trigger_msg": trigger_msg,
            "badge_color": badge_color,
            "rib_score": int(total_score),
            "components": {"struct": s_struct, "comp": s_comp, "prox": s_prox, "risk": s_risk}
        }
    except: return None

# ==========================================
# 4. News & Noise Control
# ==========================================
def analyze_news_structure(title_en):
    title_lower = title_en.lower()
    tags = []
    risk_kw = ['lawsuit', 'sec', 'probe', 'investigation', 'ban', 'fraud', 'scandal', 'breach', 'recall', 'resign']
    event_kw = ['earnings', 'revenue', 'miss', 'estimate', 'downgrade', 'guidance', 'profit']
    gov_kw = ['fda', 'ftc', 'doj', 'regulation', 'antitrust', 'policy', 'tax', 'biden', 'trump']
    macro_kw = ['fed', 'rate', 'inflation', 'cpi', 'jobs', 'sector', 'competitor', 'war', 'oil', 'yield']
    pending_kw = ['may', 'could', 'potential', 'consider', 'talks', 'rumor', 'reportedly', 'possible']

    if any(k in title_lower for k in risk_kw): tags.append(("🔴 Risk", "risk"))
    elif any(k in title_lower for k in event_kw): tags.append(("📉 Event", "event"))
    if any(k in title_lower for k in gov_kw): tags.append(("🏛️ Gov", "gov"))
    if any(k in title_lower for k in macro_kw): tags.append(("🌍 Macro", "macro"))
    if any(k in title_lower for k in pending_kw): tags.append(("❓ Pending", "pending"))
    if not tags: tags.append(("⚖️ Normal", "normal"))
    return tags

def calculate_noise_score(news_items, vol_ratio):
    noise_score = 0
    reasons = []
    has_pending = False
    has_macro = False
    has_specific = False
    is_all_normal = True
    
    if news_items:
        for item in news_items:
            for tag_txt, tag_type in item['tags']:
                if tag_type == 'pending': has_pending = True
                if tag_type == 'macro': has_macro = True
                if tag_type in ['risk', 'event', 'gov']: has_specific = True
                if tag_type != 'normal': is_all_normal = False
    
    if has_pending: 
        noise_score += 1
        reasons.append("PendingNews")
    if has_macro and not has_specific:
        noise_score += 1
        reasons.append("MacroOnly")
    if is_all_normal and news_items:
        noise_score += 1
        reasons.append("NoIssues")
    if vol_ratio > 0.05:
        noise_score += 1
        reasons.append("HighVol")
        
    return noise_score, ", ".join(reasons)

def calculate_relevance_score(title_en):
    score = 0
    if 'earnings' in title_en.lower(): score += 10
    return score

def get_google_news_rss(symbol):
    raw_news = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall('./channel/item')[:4]:
                title = item.find('title').text.rsplit(" - ", 1)[0]
                pubDate = item.find('pubDate').text[:16]
                tags = analyze_news_structure(title)
                raw_news.append({
                    "title_en": title, 
                    "link": item.find('link').text, 
                    "date_str": pubDate, 
                    "score": calculate_relevance_score(title), 
                    "tags": tags
                })
            raw_news.sort(key=lambda x: x['score'], reverse=True)
            top_news = raw_news[:2]
            translator = GoogleTranslator(source='auto', target='ko')
            for item in top_news:
                try: item['title_ko'] = translator.translate(item['title_en'])
                except: item['title_ko'] = item['title_en']
            return top_news
    except: return []
    return []

# ==========================================
# 5. Main Scan Logic (V9.3 + RIB V2)
# ==========================================
def check_hard_cut(ticker, hist):
    try:
        if hist.empty or len(hist) < 20: return False, "No Data"
        return True, "Pass"
    except: return False, "Error"

def calc_atr_and_tier(hist):
    try:
        high, low, close = hist["High"], hist["Low"], hist["Close"]
        tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(20).mean().iloc[-1]
        cur = close.iloc[-1]
        vol_ratio = atr / cur if cur > 0 else 0
        
        if vol_ratio < 0.025: return 1, -10, vol_ratio, "Tier 1"
        elif vol_ratio < 0.05: return 2, -20, vol_ratio, "Tier 2"
        else: return 3, -30, vol_ratio, "Tier 3"
    except: return 3, -30, 0, "Error"

def run_scan():
    print_system_status("🧠 [Brain] Turnaround Sniper V9.3 (Adaptive Rescue + RIB V2) 가동...")
    print(f"⚙️ Config: Score>={CUTOFF_SCORE}, Struct>={CUTOFF_STRUCT}, Noise<={CUTOFF_NOISE}")
    
    universe = build_universe()
    survivors = []
    rejected_candidates = []
    
    stats = {
        "HardCut": 0, "NotEnoughDrop": 0, 
        "F_DeepDrop": 0, "F_Score": 0, "F_Vol": 0, "F_Struct": 0, "F_Noise": 0, 
        "Pass": 0
    }
    
    print(f"\n🔍 정밀 스캔 시작 ({len(universe)}개 종목)...")

    for i, sym in enumerate(universe):
        try:
            print(f"   Scanning [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            
            t = yf.Ticker(sym)
            hist = t.history(period="6mo")
            
            if len(hist) < 120:
                stats["HardCut"] += 1
                continue
                
            passed, reason = check_hard_cut(t, hist)
            if not passed:
                stats["HardCut"] += 1
                continue

            tier, drop_limit, vol_ratio, tier_label = calc_atr_and_tier(hist)
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100

            if dd > drop_limit:
                stats["NotEnoughDrop"] += 1
                continue

            candidate_data = {
                "symbol": sym, "price": round(cur, 2), "dd": round(dd, 2),
                "tier_label": tier_label, "name": t.info.get("shortName", sym),
                "vol_ratio": vol_ratio
            }

            if dd <= CUTOFF_DEEP_DROP:
                stats["F_DeepDrop"] += 1
                continue

            # News Analysis for Noise Score calculation
            news_items = get_google_news_rss(sym)
            noise_score, noise_reason = calculate_noise_score(news_items, vol_ratio)
            candidate_data["news"] = news_items
            candidate_data["noise_score"] = noise_score
            candidate_data["noise_reason"] = noise_reason

            # RIB V2 Analysis
            rib_data = analyze_reignition_structure(hist, noise_score)
            candidate_data["rib_data"] = rib_data

            if not rib_data:
                stats["F_Score"] += 1
                continue
            
            base_a = rib_data.get('base_a', 0)
            base_b = rib_data.get('base_b', 0)
            score = rib_data.get('rib_score', 0)

            fail_reason = None
            
            # Filters
            if score < CUTOFF_SCORE:
                fail_reason = f"Score({score}) < {CUTOFF_SCORE}"
                stats["F_Score"] += 1
            elif vol_ratio > CUTOFF_VOL_RATIO:
                fail_reason = f"Vol({vol_ratio:.1%}) > {CUTOFF_VOL_RATIO:.0%}"
                stats["F_Vol"] += 1
            elif base_b < base_a * CUTOFF_STRUCT:
                ratio = base_b/base_a if base_a else 0
                fail_reason = f"Struct({ratio:.2f}) < {CUTOFF_STRUCT}"
                stats["F_Struct"] += 1
            elif noise_score > CUTOFF_NOISE:
                fail_reason = f"Noise({noise_score}) > {CUTOFF_NOISE}"
                stats["F_Noise"] += 1

            if fail_reason:
                candidate_data["fail_reason"] = fail_reason
                rejected_candidates.append(candidate_data)
                continue

            stats["Pass"] += 1
            survivors.append(candidate_data)
            
        except Exception as e:
            continue

    # 🚨 RESCUE PROTOCOL
    rescued_count = 0
    if len(survivors) < 3:
        print("\n🚨 [Rescue Protocol] 생존자 부족. Near-miss 구조대 가동!")
        rejected_candidates.sort(key=lambda x: -x.get('rib_data', {}).get('rib_score', 0))
        for cand in rejected_candidates[:10]:
            cand["is_rescue"] = True
            survivors.append(cand)
            rescued_count += 1
            print(f"   🚑 Rescued: {cand['symbol']} (Score: {cand['rib_data']['rib_score']}, Reason: {cand.get('fail_reason')})")

    # Final Sort
    survivors.sort(key=lambda x: (
        0 if not x.get("is_rescue") else 1,
        x['rib_data'].get('priority', 99) if x['rib_data'] else 99, 
        -x['rib_data'].get('rib_score', 0) if x['rib_data'] else 0
    ))
    
    print("\n" + "="*40)
    print(f"📊 [스캔 결과] 총 {len(universe)}개 중")
    print(f"   ❌ 탈락 (Hard/DD): {stats['HardCut'] + stats['NotEnoughDrop']}")
    print(f"   🔻 필터 (DeepDrop): {stats['F_DeepDrop']}")
    print(f"   🔻 필터 (Score<{CUTOFF_SCORE}): {stats['F_Score']}")
    print(f"   🔻 필터 (Vol>{CUTOFF_VOL_RATIO:.0%}): {stats['F_Vol']}")
    print(f"   🔻 필터 (Struct<{CUTOFF_STRUCT}x): {stats['F_Struct']}")
    print(f"   🔻 필터 (Noise>{CUTOFF_NOISE}): {stats['F_Noise']}")
    print(f"   ✅ 정규 생존: {stats['Pass']}")
    print(f"   🚑 구조 생존: {rescued_count}")
    print(f"   📋 최종 보고: {len(survivors)}")
    
    print("-" * 40)
    print("📜 [Rejected Log - Top 5 by Score]")
    rejected_candidates.sort(key=lambda x: -x.get('rib_data', {}).get('rib_score', 0))
    for r in rejected_candidates[:5]:
        s = r['rib_data'].get('rib_score', 0) if r.get('rib_data') else 0
        print(f"   ❌ {r['symbol']}: {r.get('fail_reason')} | Score {s}")
    print("="*40 + "\n")
    
    return survivors

# ==========================================
# 6. Dashboard Generation
# ==========================================
def generate_dashboard(targets):
    top_tier = []
    mid_tier = []
    low_tier = []
    
    for s in targets:
        rib = s.get("rib_data")
        noise = s.get("noise_score", 0)
        is_rescue = s.get("is_rescue", False)
        
        if is_rescue:
            low_tier.append(s)
        elif rib and rib.get('grade') == 'ACTION': 
            top_tier.append(s)
        elif rib and rib.get('grade') == 'SETUP' and noise < 2: 
            top_tier.append(s)
        elif rib and rib.get('grade') == 'RADAR': 
            mid_tier.append(s)
        else: 
            low_tier.append(s)

    def render_card(stock):
        sym = stock['symbol']
        rib = stock.get("rib_data") or {} 
        noise_sc = stock.get("noise_score", 0)
        noise_rs = stock.get("noise_reason", "")
        fail_rs = stock.get("fail_reason", "")
        is_rescue = stock.get("is_rescue", False)
        
        base_a = rib.get("base_a")
        pivot = rib.get("pivot")
        base_b = rib.get("base_b")
        distance = rib.get("distance")
        grade = rib.get("grade", "N/A")
        status = rib.get("status", "N/A")
        rib_score = rib.get("rib_score", 0)
        trigger_msg = rib.get("trigger_msg", "")
        comps = rib.get("components", {})

        def fmt(v):
            try: return f"${float(v):.2f}"
            except: return "N/A"
            
        def fmt_dist(v):
            try: return f"{float(v):.1f}%"
            except: return "N/A"

        rib_html = ""
        if rib:
            grade_color = {"ACTION": "#e74c3c", "SETUP": "#e67e22", "RADAR": "#f1c40f", "IGNORE": "#95a5a6"}.get(grade, "#95a5a6")
            if is_rescue: grade_color = "#7f8c8d"
            
            # Component Score Visualization
            comp_html = f"""
            <div style="display:flex; gap:5px; margin-top:8px; font-size:0.7em; color:#aaa;">
                <span title="Structure">📐{comps.get('struct',0)}</span>
                <span title="Compression">🗜️{comps.get('comp',0)}</span>
                <span title="Proximity">🎯{comps.get('prox',0)}</span>
                <span title="Risk">🛡️{comps.get('risk',0)}</span>
            </div>
            """
            
            rib_html = f"""
            <div class="rib-box" style="border-left: 4px solid {grade_color}; background: #262b3e; padding: 10px; margin-bottom: 10px; border-radius: 4px;">
                <div style="display:flex; justify-content:space-between; color:#fff; font-weight:bold; font-size:0.9em;">
                    <span>{grade} : {status}</span>
                    <span>Score: {rib_score}</span>
                </div>
                <div style="color:#d1d4dc; font-size:0.8em; margin-top:5px; display:flex; justify-content:space-between;">
                    <span>A: {fmt(base_a)} ➔ P: {fmt(pivot)} ➔ B: {fmt(base_b)}</span>
                    <span>Gap: {fmt_dist(distance)}</span>
                </div>
                {comp_html}
                <div style="font-size:0.8em; color:#f1c40f; margin-top:5px;">💡 {trigger_msg}</div>
            </div>
            """
        
        rescue_html = ""
        if is_rescue:
             rescue_html = f"<div style='background:#c0392b; color:white; padding:5px; border-radius:4px; font-size:0.8em; margin-bottom:10px; text-align:center;'>🚑 NEAR MISS: {fail_rs}</div>"

        noise_html = ""
        if noise_sc > 0:
            noise_html = f"<div style='font-size:0.75em; color:#7f8c8d; margin-bottom:5px;'>⚠️ Noise Lv.{noise_sc} ({noise_rs})</div>"

        news_html = ""
        for n in stock.get('news', []):
            tags_html = "".join([f"<span style='font-size:0.7em; background:#444; color:#fff; padding:1px 4px; border-radius:3px; margin-right:3px;'>{t[0]}</span>" for t in n.get('tags', [])])
            news_html += f"<div style='margin-bottom:4px;'><span style='font-size:0.7em; color:#aaa;'>{n.get('date_str','')}</span> {tags_html} <a href='{n.get('link','#')}' target='_blank' style='color:#d1d4dc; font-size:0.85em; text-decoration:none;'>{n.get('title_ko','')}</a></div>"
        if not news_html: news_html = "<div style='font-size:0.8em; color:#666;'>No recent news</div>"

        tm_link = ""
        base_a_date = rib.get("base_a_date")
        base_b_date = rib.get("base_b_date")
        if base_a_date and base_b_date:
            tm_link = f"<a href='https://www.google.com/search?q={sym}+stock+news+after:{base_a_date}+before:{base_b_date}' target='_blank' style='display:block; text-align:center; background:#2a2e39; color:#aaa; font-size:0.75em; padding:4px; margin-top:5px; text-decoration:none; border-radius:3px;'>🕒 TimeMachine Check</a>"

        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        
        return f"""
        <div class="card">
            <div class="card-header">
                <span class="sym">{sym}</span> <span class="name">{stock.get('name','')}</span>
                <span class="price">${stock.get('price',0)}</span>
                <span class="badge" style="background:#333;">{stock.get('tier_label','')}</span>
                <span class="badge" style="background:#444;">{stock.get('dd',0):.1f}%</span>
            </div>
            <div class="card-body">
                <div class="info-col">
                    {rescue_html}
                    {rib_html}
                    {noise_html}
                    <div class="news-box">{news_html}</div>
                    {tm_link}
                </div>
                <div class="chart-col">
                    <div class="tradingview-widget-container">
                        <div id="{chart_id}" style="height:250px;"></div>
                        <script type="text/javascript">
                            new TradingView.widget({{
                                "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC", "theme": "dark", "style": "1", "locale": "en", "hide_top_toolbar": true, "container_id": "{chart_id}"
                            }});
                        </script>
                    </div>
                </div>
            </div>
        </div>
        """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sniper V9.3 Adaptive</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <style>
            body {{ background: #131722; color: #d1d4dc; font-family: sans-serif; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; color: #e67e22; }}
            .config-bar {{ background: #1e222d; padding: 10px; border-radius: 6px; text-align: center; margin-bottom: 20px; font-size: 0.9em; color: #aaa; border: 1px solid #2a2e39; }}
            details {{ margin-bottom: 20px; background: #1e222d; border-radius: 8px; overflow: hidden; }}
            summary {{ padding: 15px; background: #2a2e39; cursor: pointer; font-weight: bold; list-style: none; }}
            summary:hover {{ background: #363c4e; }}
            .section-content {{ padding: 15px; display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 15px; }}
            .card {{ background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px; overflow: hidden; }}
            .card-header {{ padding: 10px; background: #262b3e; border-bottom: 1px solid #2a2e39; display: flex; align-items: center; gap: 10px; }}
            .sym {{ font-size: 1.2em; font-weight: bold; color: #fff; }}
            .name {{ font-size: 0.8em; color: #777; flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .badge {{ font-size: 0.7em; padding: 2px 5px; border-radius: 3px; }}
            .card-body {{ display: flex; height: 350px; }}
            .info-col {{ flex: 4; padding: 10px; overflow-y: auto; border-right: 1px solid #2a2e39; }}
            .chart-col {{ flex: 6; }}
            .news-box {{ margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V9.3 <span style="font-size:0.6em; color:#aaa;">ADAPTIVE RESCUE + RIB V2</span></h1>
            
            <div class="config-bar">
                ⚙️ Config: Score>={CUTOFF_SCORE} | Struct>={CUTOFF_STRUCT}x | Noise<={CUTOFF_NOISE} | Rescue: ON
            </div>
            
            <details open>
                <summary>🏆 TOP TIER (Action & Setup) - {len(top_tier)} Targets</summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in top_tier])}
                </div>
            </details>

            <details>
                <summary>📡 MID TIER (Radar Watch) - {len(mid_tier)} Targets</summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in mid_tier])}
                </div>
            </details>

            <details>
                <summary>🚑 LOW TIER & NEAR MISS - {len(low_tier)} Targets</summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in low_tier])}
                </div>
            </details>
        </div>
    </body>
    </html>
    """

    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

# ==========================================
# 7. 실행 엔트리 포인트 (필수)
# ==========================================
if __name__ == "__main__":
    print_system_status("🚀 Sniper Engine Started...")
    try:
        targets = run_scan()
        generate_dashboard(targets)
        print_system_status("✅ Workflow Complete. Dashboard generated.")
    except Exception as e:
        print_system_status(f"❌ Fatal Error: {e}")
        sys.exit(1)
