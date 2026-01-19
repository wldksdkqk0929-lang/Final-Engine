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
# 0. 시스템 설정
# ==========================================
def print_system_status(msg):
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

# ---------------------------------------------------------
# ⚙️ 필터 설정 (V9.4 News Engine Upgrade)
# ---------------------------------------------------------
UNIVERSE_MAX = 150
CUTOFF_SCORE = 65       # (완화 유지)
CUTOFF_STRUCT = 1.05    # Base B >= Base A * 1.05
CUTOFF_NOISE = 2        # Noise Score limit
CUTOFF_VOL_RATIO = 0.06 
CUTOFF_DEEP_DROP = -55  
# ---------------------------------------------------------

ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]
CORE_WATCHLIST = [
    "DKNG", "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "ROKU", "SQ",
    "COIN", "MSTR", "CVNA", "U", "RBLX", "PATH", "AI", "IONQ", "HIMS"
]

# ==========================================
# 1. Universe Builder
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
        except: continue
    return list(symbols)

def build_universe():
    print_system_status("🏗️ [Universe Builder] 유니버스 구축 시작...")
    candidates = fetch_nasdaq_symbols()
    if len(candidates) < 10:
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
        except: continue
        print(f"   Running.. {min(i+chunk_size, len(scan_targets))}/{len(scan_targets)} verified", end="\r")

    liquidity_scores.sort(key=lambda x: x[1], reverse=True)
    top_n = liquidity_scores[:UNIVERSE_MAX]
    final_universe = [x[0] for x in top_n]
    for core in CORE_WATCHLIST:
        if core not in final_universe: final_universe.append(core)
    final_universe = list(set(final_universe))
    print(f"\n✅ [Universe] 최종 확정: {len(final_universe)}개 종목")
    return final_universe

# ==========================================
# 2. RIB V2 Engine (Scoring)
# ==========================================
def calculate_structure_quality(base_a, base_b, base_a_date, base_b_date):
    try:
        score = 0
        if base_a == 0: return 0
        ratio = base_b / base_a
        if 1.03 <= ratio <= 1.15: score += 15
        elif 1.00 < ratio < 1.03: score += 5
        elif ratio > 1.15: score += 7
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
        high_low = hist["High"] - hist["Low"]
        atr_recent = high_low.tail(10).mean()
        atr_past = high_low.tail(60).mean()
        if atr_past == 0: return 0
        atr_ratio = atr_recent / atr_past
        
        if atr_ratio < 0.7: score += 15
        elif atr_ratio < 0.9: score += 10
        elif atr_ratio < 1.1: score += 5
        
        vol_recent = hist["Volume"].tail(10).mean()
        vol_past = hist["Volume"].tail(60).mean()
        vol_ratio = vol_recent / vol_past if vol_past > 0 else 1
        
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
        
        # V9.4: Noise Score가 0보다 작으면(회복 신호) 감점 없음/보너스
        if noise_score > 0:
            score -= (noise_score * 5)
        
        return max(0, score)
    except: return 0

def analyze_reignition_structure(hist, noise_score=0):
    try:
        if len(hist) < 120: return None
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
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

        if base_b_price < base_a_price:
            return {"status": "INVALID (Low Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}
        if current_price < base_b_price:
            return {"status": "INVALID (B Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}

        s_struct = calculate_structure_quality(base_a_price, base_b_price, base_a_date, base_b_date)
        s_comp = calculate_compression_energy(hist)
        s_prox = calculate_breakout_proximity(current_price, pivot_price, hist)
        s_risk = calculate_risk_stability(current_price, hist, noise_score)
        total_score = s_struct + s_comp + s_prox + s_risk
        
        if pivot_price == 0: dist_pct = 0
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        status = ""
        grade = "IGNORE"
        priority = 4
        trigger_msg = ""

        if current_price > pivot_price:
            status = "🔥 RIB BREAKOUT"
            grade = "ACTION"
            priority = 1
            trigger_msg = "Pivot 돌파. 모멘텀 발생."
        elif dist_pct <= 3.0:
            status = "🚀 RIB READY"
            grade = "SETUP"
            priority = 2
            trigger_msg = f"돌파 임박 ({dist_pct:.1f}%)."
        elif dist_pct <= 10.0:
            status = "👀 RIB WATCH"
            grade = "RADAR"
            priority = 3
            trigger_msg = f"구조 형성 중 ({dist_pct:.1f}%)."
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
            "rib_score": int(total_score),
            "components": {"struct": s_struct, "comp": s_comp, "prox": s_prox, "risk": s_risk}
        }
    except: return None

# ==========================================
# 3. Advanced News Engine (V9.4)
# ==========================================
def fetch_news_from_google(symbol, start_date=None, end_date=None, label="Recent"):
    """
    특정 기간의 뉴스를 Google RSS로 수집
    """
    news_items = []
    try:
        query = f"{symbol} stock"
        if start_date: query += f" after:{start_date}"
        if end_date: query += f" before:{end_date}"
        
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=4)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall('./channel/item')[:3]: # 기간별 최대 3개
                title = item.find('title').text.rsplit(" - ", 1)[0]
                pubDate = item.find('pubDate').text[:16]
                link = item.find('link').text
                
                # 중복 방지 키
                news_items.append({
                    "title": title, "link": link, "date": pubDate, "label": label
                })
    except: pass
    return news_items

def classify_news_semantics(title):
    """
    [V9.4] 뉴스 구조적 분류 (Structural vs Event vs Recovery)
    """
    title_lower = title.lower()
    
    # 1. Structural Risk (심각한 악재)
    struct_risk_kw = ['fraud', 'investigation', 'sec probe', 'lawsuit', 'bankruptcy', 'delisting', 'breach', 'scandal', 'fake', 'manipulation']
    if any(k in title_lower for k in struct_risk_kw):
        return "🔴 Structural Risk", "risk"
        
    # 2. Recovery Signal (호재/회복)
    recovery_kw = ['upgrade', 'beat', 'partnership', 'agreement', 'launch', 'approval', 'fda approved', 'record', 'growth', 'expansion', 'buyback']
    if any(k in title_lower for k in recovery_kw):
        return "🟢 Recovery Signal", "good"

    # 3. One-time Event (일시적)
    event_kw = ['miss', 'earnings', 'revenue', 'guidance', 'downgrade', 'weather', 'outage']
    if any(k in title_lower for k in event_kw):
        return "🟠 One-time Event", "event"

    # 4. Macro/Noise
    macro_kw = ['fed', 'rate', 'inflation', 'sector', 'market', 'yield', 'oil', 'competitor']
    if any(k in title_lower for k in macro_kw):
        return "🌍 Macro/Noise", "macro"
        
    return "⚖️ General", "normal"

def analyze_deep_news_context(symbol, rib_data):
    """
    [V9.4] Dual-Phase News Analysis
    - Phase A: Crash Context (Base A 전후)
    - Phase B: Recovery Context (Base B 이후)
    """
    if not rib_data: return [], 0, "No Data"
    
    base_a_date = rib_data['base_a_date']
    base_b_date = rib_data['base_b_date']
    
    # 날짜 계산
    dt_a = datetime.strptime(base_a_date, "%Y-%m-%d")
    dt_b = datetime.strptime(base_b_date, "%Y-%m-%d")
    
    # Phase A: Crash (Base A - 7일 ~ Base A + 14일)
    start_a = (dt_a - timedelta(days=7)).strftime("%Y-%m-%d")
    end_a = (dt_a + timedelta(days=14)).strftime("%Y-%m-%d")
    
    # Phase B: Recovery (Base B ~ Now)
    start_b = base_b_date
    
    # Fetch
    news_crash = fetch_news_from_google(symbol, start_a, end_a, "📉 낙폭 원인")
    news_recovery = fetch_news_from_google(symbol, start_b, None, "🔄 최근 동향")
    
    all_news = news_crash + news_recovery
    
    # Translate & Classify
    processed_news = []
    translator = GoogleTranslator(source='auto', target='ko')
    
    current_noise_score = 0
    noise_reasons = []
    
    for item in all_news:
        try: item['title_ko'] = translator.translate(item['title'])
        except: item['title_ko'] = item['title']
        
        cat_text, cat_type = classify_news_semantics(item['title'])
        item['category_text'] = cat_text
        item['category_type'] = cat_type
        
        # [V9.4] Smart Noise Scoring
        # 과거(낙폭 원인) 뉴스는 노이즈 점수에 반영하지 않음
        # 현재(최근 동향) 뉴스만 반영
        if item['label'] == "🔄 최근 동향":
            if cat_type == 'risk':
                current_noise_score += 3 # 구조적 악재는 치명적
                noise_reasons.append("Structural Risk")
            elif cat_type == 'event':
                current_noise_score += 1 # 일회성은 가벼운 노이즈
            elif cat_type == 'good':
                current_noise_score -= 1 # 호재는 노이즈 상쇄 (보너스)
                
        processed_news.append(item)
    
    # Score Clipping
    current_noise_score = max(0, current_noise_score)
    noise_reason_str = ", ".join(list(set(noise_reasons))) if noise_reasons else "Stable"
    
    return processed_news, current_noise_score, noise_reason_str

# ==========================================
# 4. Main Scan Logic
# ==========================================
def run_scan():
    print_system_status("🧠 [Brain] Turnaround Sniper V9.4 (Deep News Context) 가동...")
    print(f"⚙️ Config: Score>={CUTOFF_SCORE}, Struct>={CUTOFF_STRUCT}, Noise<={CUTOFF_NOISE}")
    
    universe = build_universe()
    survivors = []
    rejected = []
    
    print(f"\n🔍 정밀 스캔 시작 ({len(universe)}개 종목)...")

    for i, sym in enumerate(universe):
        try:
            print(f"   Scanning [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            
            t = yf.Ticker(sym)
            hist = t.history(period="6mo")
            if len(hist) < 120: continue
            
            # 1. Basic Filters
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100
            
            # Deep Drop Cut
            if dd <= CUTOFF_DEEP_DROP: continue
            
            # 2. RIB Analysis (1차)
            rib_data = analyze_reignition_structure(hist, noise_score=0) # 노이즈 점수 없이 일단 구조 분석
            if not rib_data: continue

            # 3. 1차 컷오프 (Score & Struct) - API 절약을 위해 여기서 먼저 거름
            # 단, Noise 점수가 아직 없으므로 Score는 Risk 제외 점수임. 약간 여유있게 통과시킴
            pre_score = rib_data['rib_score']
            base_a = rib_data['base_a']
            base_b = rib_data['base_b']
            
            if base_b < base_a * CUTOFF_STRUCT: continue # 구조 미달은 즉시 탈락
            if pre_score < (CUTOFF_SCORE - 10): continue # 점수가 너무 낮으면 뉴스 볼 필요도 없음

            # 4. Deep News Analysis (생존 가능성 높은 놈들만)
            news_items, noise_score, noise_reason = analyze_deep_news_context(sym, rib_data)
            
            # 5. Final RIB Scoring (Noise 반영)
            final_rib = analyze_reignition_structure(hist, noise_score)
            
            # ATR check
            high_low = hist["High"] - hist["Low"]
            atr = high_low.tail(20).mean()
            vol_ratio = atr / cur if cur > 0 else 0
            
            # Final Filter Check
            fail_reason = None
            if final_rib['rib_score'] < CUTOFF_SCORE: fail_reason = f"Score {final_rib['rib_score']}"
            elif vol_ratio > CUTOFF_VOL_RATIO: fail_reason = f"Vol {vol_ratio:.1%}"
            elif noise_score > CUTOFF_NOISE: fail_reason = f"Noise {noise_score}"
            
            cand_data = {
                "symbol": sym, "price": round(cur, 2), "dd": round(dd, 2),
                "name": t.info.get("shortName", sym),
                "rib_data": final_rib,
                "news": news_items,
                "noise_score": noise_score,
                "noise_reason": noise_reason,
                "fail_reason": fail_reason
            }

            if fail_reason:
                rejected.append(cand_data)
            else:
                survivors.append(cand_data)

        except: continue

    # Rescue Protocol
    if len(survivors) < 3:
        print("\n🚨 [Rescue Protocol] 생존자 부족. Near-miss 구조대 가동!")
        rejected.sort(key=lambda x: -x['rib_data']['rib_score'])
        for cand in rejected[:10]:
            cand["is_rescue"] = True
            survivors.append(cand)

    # Final Sort
    survivors.sort(key=lambda x: (
        0 if not x.get("is_rescue") else 1,
        x['rib_data'].get('priority', 99), 
        -x['rib_data'].get('rib_score', 0)
    ))
    
    print(f"\n✅ 최종 보고: {len(survivors)}개 종목")
    return survivors

# ==========================================
# 5. Dashboard (Split View)
# ==========================================
def generate_dashboard(targets):
    top_tier = []
    mid_tier = []
    low_tier = []
    
    for s in targets:
        rib = s.get("rib_data")
        noise = s.get("noise_score", 0)
        is_rescue = s.get("is_rescue", False)
        
        if is_rescue: low_tier.append(s)
        elif rib and rib.get('grade') == 'ACTION': top_tier.append(s)
        elif rib and rib.get('grade') == 'SETUP' and noise < 2: top_tier.append(s)
        elif rib and rib.get('grade') == 'RADAR': mid_tier.append(s)
        else: low_tier.append(s)

    def render_card(stock):
        sym = stock['symbol']
        rib = stock.get("rib_data") or {} 
        noise_sc = stock.get("noise_score", 0)
        comps = rib.get("components", {})
        is_rescue = stock.get("is_rescue", False)
        
        # News Split Rendering
        news_crash_html = ""
        news_recovery_html = ""
        
        for n in stock.get('news', []):
            cat_color = {"risk": "#c0392b", "good": "#27ae60", "event": "#e67e22", "macro": "#7f8c8d", "normal": "#555"}.get(n['category_type'], "#555")
            tag_html = f"<span style='font-size:0.7em; background:{cat_color}; color:#fff; padding:1px 4px; border-radius:3px; margin-right:3px;'>{n['category_text']}</span>"
            item_html = f"<div style='margin-bottom:4px;'><span style='font-size:0.7em; color:#aaa;'>{n['date']}</span> {tag_html} <a href='{n['link']}' target='_blank' style='color:#d1d4dc; font-size:0.85em; text-decoration:none;'>{n['title_ko']}</a></div>"
            
            if n['label'] == "📉 낙폭 원인": news_crash_html += item_html
            else: news_recovery_html += item_html

        if not news_crash_html: news_crash_html = "<div style='color:#666; font-size:0.8em;'>관련 뉴스 없음</div>"
        if not news_recovery_html: news_recovery_html = "<div style='color:#666; font-size:0.8em;'>관련 뉴스 없음</div>"

        # RIB UI
        grade = rib.get("grade", "N/A")
        grade_color = {"ACTION": "#e74c3c", "SETUP": "#e67e22", "RADAR": "#f1c40f", "IGNORE": "#95a5a6"}.get(grade, "#95a5a6")
        if is_rescue: grade_color = "#7f8c8d"

        rescue_badge = f"<div style='background:#c0392b; color:white; padding:5px; border-radius:4px; font-size:0.8em; margin-bottom:10px; text-align:center;'>🚑 NEAR MISS: {stock.get('fail_reason')}</div>" if is_rescue else ""
        
        comp_html = f"""
        <div style="display:flex; gap:10px; margin-top:8px; font-size:0.75em; color:#aaa; justify-content:center; background:#222; padding:5px; border-radius:4px;">
            <span title="Structure">📐 {comps.get('struct',0)}</span>
            <span title="Compression">🗜️ {comps.get('comp',0)}</span>
            <span title="Proximity">🎯 {comps.get('prox',0)}</span>
            <span title="Risk Stability">🛡️ {comps.get('risk',0)}</span>
        </div>
        """

        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        
        return f"""
        <div class="card">
            <div class="card-header">
                <span class="sym">{sym}</span> <span class="name">{stock.get('name','')}</span>
                <span class="price">${stock.get('price',0)}</span>
                <span class="badge" style="background:#444;">{stock.get('dd',0):.1f}%</span>
            </div>
            <div class="card-body">
                <div class="info-col">
                    {rescue_badge}
                    <div class="rib-box" style="border-left: 4px solid {grade_color}; background: #262b3e; padding: 10px; margin-bottom: 10px; border-radius: 4px;">
                        <div style="display:flex; justify-content:space-between; color:#fff; font-weight:bold; font-size:0.9em;">
                            <span>{grade} : {rib.get('status')}</span>
                            <span>Total: {rib.get('rib_score')}</span>
                        </div>
                        {comp_html}
                        <div style="font-size:0.8em; color:#f1c40f; margin-top:5px;">💡 {rib.get('trigger_msg')}</div>
                    </div>
                    
                    <div class="news-container">
                        <div class="news-col" style="border-right:1px solid #333; padding-right:5px;">
                            <h5 style="margin:5px 0; color:#e74c3c;">📉 낙폭 원인 (Crash)</h5>
                            {news_crash_html}
                        </div>
                        <div class="news-col" style="padding-left:5px;">
                            <h5 style="margin:5px 0; color:#2ecc71;">🔄 최근 동향 (Recovery)</h5>
                            {news_recovery_html}
                        </div>
                    </div>
                </div>
                <div class="chart-col">
                    <div class="tradingview-widget-container">
                        <div id="{chart_id}" style="height:350px;"></div>
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
        <title>Sniper V9.4 Deep Context</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <style>
            body {{ background: #131722; color: #d1d4dc; font-family: sans-serif; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; color: #e67e22; }}
            details {{ margin-bottom: 20px; background: #1e222d; border-radius: 8px; overflow: hidden; }}
            summary {{ padding: 15px; background: #2a2e39; cursor: pointer; font-weight: bold; list-style: none; }}
            summary:hover {{ background: #363c4e; }}
            .section-content {{ padding: 15px; display: grid; grid-template-columns: 1fr; gap: 15px; }}
            .card {{ background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px; overflow: hidden; }}
            .card-header {{ padding: 10px; background: #262b3e; border-bottom: 1px solid #2a2e39; display: flex; align-items: center; gap: 10px; }}
            .sym {{ font-size: 1.2em; font-weight: bold; color: #fff; }}
            .name {{ font-size: 0.8em; color: #777; flex-grow: 1; }}
            .badge {{ font-size: 0.7em; padding: 2px 5px; border-radius: 3px; }}
            .card-body {{ display: flex; height: 400px; }}
            .info-col {{ flex: 5; padding: 10px; overflow-y: auto; border-right: 1px solid #2a2e39; display: flex; flex-direction: column; }}
            .chart-col {{ flex: 5; }}
            .news-container {{ display: flex; flex: 1; margin-top: 10px; border-top: 1px solid #333; padding-top: 10px; }}
            .news-col {{ flex: 1; overflow-y: auto; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V9.4 <span style="font-size:0.6em; color:#aaa;">DEEP NEWS CONTEXT</span></h1>
            <div style="text-align:center; color:#777; margin-bottom:20px;">
                ⚙️ Config: Score>={CUTOFF_SCORE} | Struct>={CUTOFF_STRUCT}x | Noise<={CUTOFF_NOISE}
            </div>
            
            <details open>
                <summary>🏆 TOP TIER (Action & Setup) - {len(top_tier)} Targets</summary>
                <div class="section-content">{"".join([render_card(s) for s in top_tier])}</div>
            </details>
            <details>
                <summary>📡 MID TIER (Radar Watch) - {len(mid_tier)} Targets</summary>
                <div class="section-content">{"".join([render_card(s) for s in mid_tier])}</div>
            </details>
            <details>
                <summary>🚑 LOW TIER & NEAR MISS - {len(low_tier)} Targets</summary>
                <div class="section-content">{"".join([render_card(s) for s in low_tier])}</div>
            </details>
        </div>
    </body>
    </html>
    """

    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

if __name__ == "__main__":
    print_system_status("🚀 Sniper Engine Started...")
    try:
        targets = run_scan()
        generate_dashboard(targets)
        print_system_status("✅ Workflow Complete.")
    except Exception as e:
        print_system_status(f"❌ Fatal Error: {e}")
        sys.exit(1)
