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
# 0. 시스템 설정 & 캐시
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

# 번역 캐시 (중복 방지)
TRANSLATION_CACHE = {}

# ---------------------------------------------------------
# ⚙️ V10.5 설정 (Structure First / Full Universe / Optimization)
# ---------------------------------------------------------
UNIVERSE_TOP_FIXED = 150    # 유동성 최상위 고정
UNIVERSE_RANDOM = 200       # 유동성 차상위 랜덤 샘플
CUTOFF_SCORE = 65           # 최소 RIB 점수
CUTOFF_DEEP_DROP = -55      # 지하실 컷
NEWS_SCAN_THRESHOLD = 75    # 이 점수 이상이거나 ACTION/SETUP일 때만 뉴스 검색
# ---------------------------------------------------------

ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]
CORE_WATCHLIST = [
    "DKNG", "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "ROKU", "SQ",
    "COIN", "MSTR", "CVNA", "U", "RBLX", "PATH", "AI", "IONQ", "HIMS"
]

# ==========================================
# 1. Universe Builder (US Full Market)
# ==========================================
def fetch_us_market_symbols():
    symbols = set()
    # NASDAQ + Other Listed (NYSE/AMEX etc)
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
    ]
    print_status("🌐 [Universe] 미국 전체 거래소 리스트 수집 중...")
    
    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                df = pd.read_csv(StringIO(resp.text), sep="|")
                # 필터: Test Issue 제거, ETF 제거
                if 'Test Issue' in df.columns: df = df[df['Test Issue'] == 'N']
                if 'ETF' in df.columns: df = df[df['ETF'] == 'N']
                
                raw_syms = df['Symbol'].dropna().astype(str).tolist()
                
                # 정규식 필터: 알파벳+점(.) 허용, 길이 1~5 (예: BRK.B 허용)
                # 기존 isalpha()는 '.'을 거부하므로 정규식으로 변경
                valid_pattern = re.compile(r"^[A-Z\.]+$")
                
                for s in raw_syms:
                    s_clean = s.strip().upper()
                    if valid_pattern.match(s_clean) and len(s_clean) <= 5:
                        symbols.add(s_clean)
        except Exception as e:
            print_status(f"⚠️ 리스트 다운로드 에러: {e}")
            continue
            
    return list(symbols)

def build_universe():
    print_status("🏗️ [Universe Builder] 유동성 기반 풀 구성 (Top + Random)...")
    
    candidates = fetch_us_market_symbols()
    if len(candidates) < 100:
        print_status("⚠️ 데이터 부족. 기본 리스트 사용.")
        candidates = list(set(CORE_WATCHLIST + ["AAPL", "MSFT", "TSLA", "NVDA", "AMD", "AMZN", "GOOGL"]))
    else:
        # Core는 무조건 포함
        candidates = list(set(candidates + CORE_WATCHLIST))

    print(f"   📋 1차 후보군: {len(candidates)}개 -> 유동성 분석 시작 (Batch)...")
    
    # 유동성 분석을 위한 배치 다운로드 (최근 5일치만)
    liquidity_scores = []
    
    # API 호출 최적화를 위해 전체 다 하지 않고, Core + 랜덤 1000개만 샘플링해서 유동성 체크
    # (전수조사는 시간이 너무 걸림)
    scan_pool = list(set(candidates) - set(CORE_WATCHLIST))
    random.shuffle(scan_pool)
    check_targets = CORE_WATCHLIST + scan_pool[:1200] 
    
    chunk_size = 400 # 덩어리로 요청
    for i in range(0, len(check_targets), chunk_size):
        chunk = check_targets[i:i+chunk_size]
        try:
            # 배치 다운로드
            data = yf.download(chunk, period="5d", group_by='ticker', threads=True, progress=False)
            
            # yfinance 결과 처리 (MultiIndex vs Single)
            if len(chunk) == 1:
                # 단일 종목일 경우 구조가 다름, 리스트로 감싸서 처리
                sym = chunk[0]
                if not data.empty:
                    avg_vol = (data['Close'] * data['Volume']).mean()
                    liquidity_scores.append((sym, 0 if pd.isna(avg_vol) else avg_vol))
            else:
                # 다중 종목
                for sym in chunk:
                    try:
                        df = data[sym]
                        if df.empty: continue
                        avg_vol = (df['Close'] * df['Volume']).mean()
                        liquidity_scores.append((sym, 0 if pd.isna(avg_vol) else avg_vol))
                    except: continue
        except: continue
        print(f"   ⚖️ Liquidity Check: {min(i+chunk_size, len(check_targets))}/{len(check_targets)}", end="\r")

    # 정렬 및 선별 (이원화 전략)
    liquidity_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 1. Top Fixed (상위 150개)
    top_fixed = [x[0] for x in liquidity_scores[:UNIVERSE_TOP_FIXED]]
    
    # 2. Random Sample (그 다음 구간 450개 중 200개 랜덤)
    next_pool = [x[0] for x in liquidity_scores[UNIVERSE_TOP_FIXED : UNIVERSE_TOP_FIXED+450]]
    if len(next_pool) > UNIVERSE_RANDOM:
        random_picked = random.sample(next_pool, UNIVERSE_RANDOM)
    else:
        random_picked = next_pool
        
    final_set = set(top_fixed + random_picked + CORE_WATCHLIST)
    final_list = list(final_set)
    
    print(f"\n✅ [Universe] 최종 확정: {len(final_list)}개 (Top {UNIVERSE_TOP_FIXED} + Random {len(random_picked)} + Core)")
    return final_list

# ==========================================
# 2. RIB V2 Engine (Logic 유지)
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

def calculate_risk_stability(current_price, hist):
    try:
        score = 20
        high_low = hist["High"] - hist["Low"]
        atr = high_low.tail(20).mean()
        vol_ratio = atr / current_price if current_price > 0 else 0
        if vol_ratio > 0.05: score -= 5
        if vol_ratio > 0.08: score -= 5
        return max(0, score)
    except: return 0

def analyze_reignition_structure(hist):
    try:
        if len(hist) < 120: return None
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]
        base_a_date = base_a_idx.strftime("%Y-%m-%d")
        
        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5: return None 

        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]
        pivot_date = pivot_idx.strftime("%Y-%m-%d")
        
        if pivot_date == base_a_date: return None

        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3: return None 

        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]
        base_b_date = base_b_idx.strftime("%Y-%m-%d")

        if base_b_price < base_a_price: return {"status": "INVALID_LOW", "rib_score": 0}
        if current_price < base_b_price: return {"status": "INVALID_BROKEN", "rib_score": 0}

        s_struct = calculate_structure_quality(base_a_price, base_b_price, base_a_date, base_b_date)
        s_comp = calculate_compression_energy(hist)
        s_prox = calculate_breakout_proximity(current_price, pivot_price, hist)
        s_risk = calculate_risk_stability(current_price, hist)
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

        pre_base_a = hist.loc[:base_a_idx]
        if not pre_base_a.empty:
            peak_idx = pre_base_a["High"].tail(120).idxmax()
            peak_date = peak_idx.strftime("%Y-%m-%d")
        else:
            peak_date = (base_a_idx - timedelta(days=60)).strftime("%Y-%m-%d")

        return {
            "base_a": base_a_price, "base_a_date": base_a_date,
            "pivot": pivot_price, "pivot_date": pivot_date,
            "base_b": base_b_price, "base_b_date": base_b_date,
            "peak_date": peak_date,
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
# 3. Narrative Engine (Optimized & Cached)
# ==========================================
def translate_cached(text, translator):
    if text in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[text]
    try:
        res = translator.translate(text)
        TRANSLATION_CACHE[text] = res
        return res
    except: return text

def classify_news_semantics(title, context_type):
    title_lower = title.lower()
    if context_type == "DROP":
        if any(k in title_lower for k in ['fraud', 'investigation', 'sec probe', 'lawsuit', 'bankruptcy', 'delisting', 'scandal', 'breach']):
            return "🔴 Structural Risk", "risk", 30 
        if any(k in title_lower for k in ['miss', 'earnings', 'revenue', 'guidance', 'downgrade', 'cut', 'slumps', 'plunge', 'tumble']):
            return "📉 Event Shock", "event", 20 
        if any(k in title_lower for k in ['fed', 'inflation', 'market', 'yield', 'sector']):
            return "🌍 Macro Noise", "macro", 5 
        return "📉 Drop Factor", "event", 10
    elif context_type == "RECOVERY":
        good_kw = ['upgrade', 'beat', 'raise', 'partnership', 'approval', 'record', 'buyback', 'jump', 'soar', 'contract', 'expansion', 'restructuring', 'cost cut', 'margin', 'profitability', 'turnaround', 'initiates', 'target price', 'outperform', 'rebound', 'new product']
        if any(k in title_lower for k in good_kw):
            return "🟢 Recovery Signal", "good", 30
        if any(k in title_lower for k in ['fall', 'drop', 'cut', 'lawsuit', 'sell']):
            return "⚠️ Risk Lingering", "bad", -10
        return "⚖️ General News", "neutral", 0
    return "News", "neutral", 0

def fetch_filtered_news(symbol, start_date, end_date, context_type):
    items = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            translator = GoogleTranslator(source='auto', target='ko')
            target_start = datetime.strptime(start_date, "%Y-%m-%d")
            target_end = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
            count = 0
            for item in root.findall('./channel/item')[:20]: 
                try:
                    pubDateStr = item.find('pubDate').text
                    try: pubDate = datetime.strptime(pubDateStr[:16], "%a, %d %b %Y")
                    except: continue 
                    if not (target_start <= pubDate <= target_end + timedelta(days=1)): continue
                    title = item.find('title').text.rsplit(" - ", 1)[0]
                    link = item.find('link').text
                    if any(x['title'] == title for x in items): continue
                    
                    title_ko = translate_cached(title, translator)
                    cat_text, cat_type, weight = classify_news_semantics(title, context_type)
                    if context_type == "DROP" and cat_type == "macro": continue

                    items.append({"title": title, "title_ko": title_ko, "link": link, "date": pubDate.strftime("%Y-%m-%d"), "category": cat_text, "type": cat_type, "weight": weight})
                    count += 1
                    if count >= 3: break 
                except: continue
    except: pass
    return items

def analyze_narrative_score(symbol, rib_data):
    empty_result = {"drop_news": [], "recovery_news": [], "narrative_score": 0, "status_label": "⚠️ Info Needed"}
    if not rib_data: return empty_result
    try:
        drop_start = rib_data['peak_date']
        dt_a = datetime.strptime(rib_data['base_a_date'], "%Y-%m-%d")
        drop_end = (dt_a + timedelta(days=3)).strftime("%Y-%m-%d")
        rec_start = rib_data['base_b_date']
        
        drop_news = fetch_filtered_news(symbol, drop_start, drop_end, "DROP")
        rec_news = fetch_filtered_news(symbol, rec_start, None, "RECOVERY")
        
        drop_score = sum(n['weight'] for n in drop_news)
        rec_score = sum(n['weight'] for n in rec_news)
        total_score = min(50, drop_score) + min(50, rec_score)
        
        if total_score >= 60: label = f"🔥 Strong ({total_score})"
        elif total_score >= 30: label = f"⚖️ Neutral ({total_score})"
        else: label = f"⚠️ Weak ({total_score})"
        
        return {"drop_news": drop_news, "recovery_news": rec_news, "narrative_score": int(total_score), "status_label": label}
    except: return empty_result

# ==========================================
# 4. Main Scan Logic (Batch Optimized)
# ==========================================
def run_scan():
    print_status("🧠 [Brain] SNIPER V10.5 (Optimized Batch Scan) 가동...")
    
    universe = build_universe()
    survivors = []
    
    print(f"\n🔍 배치 스캔 시작 ({len(universe)}개)...")
    
    batch_size = 50 # yfinance 최적화 배치 사이즈
    
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i+batch_size]
        print(f"   🚀 Scanning Batch {i//batch_size + 1} ({len(batch)} symbols)...", end="\r")
        
        try:
            # 1년치 데이터 한 번에 다운로드
            data = yf.download(batch, period="1y", group_by='ticker', threads=True, progress=False)
            
            for sym in batch:
                try:
                    # 데이터 추출
                    if len(batch) == 1: df = data
                    else: df = data[sym]
                    
                    if len(df) < 230: continue # 데이터 부족
                    
                    # 1. Basic Filters
                    high_120 = df["High"].tail(120).max()
                    cur = df["Close"].iloc[-1]
                    dd = ((cur - high_120) / high_120) * 100
                    
                    if dd <= CUTOFF_DEEP_DROP: continue
                    
                    # 2. RIB Analysis
                    rib_data = analyze_reignition_structure(df)
                    if not rib_data: continue
                    if rib_data['rib_score'] < CUTOFF_SCORE: continue

                    # 3. Narrative Analysis (조건부 실행 - 최적화)
                    # 점수가 높거나 등급이 좋은 경우만 뉴스 검색
                    grade = rib_data.get('grade', 'IGNORE')
                    score = rib_data.get('rib_score', 0)
                    
                    narrative = {"drop_news": [], "recovery_news": [], "narrative_score": 0, "status_label": "Skipped"}
                    
                    if score >= NEWS_SCAN_THRESHOLD or grade in ['ACTION', 'SETUP', 'RADAR']:
                        narrative = analyze_narrative_score(sym, rib_data)
                    
                    survivors.append({
                        "symbol": sym, "price": round(cur, 2), "dd": round(dd, 2),
                        "name": sym, # yfinance 배치에서는 info 가져오기 어려움 (속도 저하 원인)
                        "rib_data": rib_data,
                        "narrative": narrative
                    })
                except Exception as e: continue
        except Exception as e: continue

    survivors.sort(key=lambda x: (
        x['rib_data'].get('priority', 99), 
        -x['rib_data'].get('rib_score', 0),
        -x['narrative']['narrative_score']
    ))
    
    print(f"\n✅ 최종 분석 완료: {len(survivors)}개 종목 보고")
    return survivors

# ==========================================
# 5. Dashboard Generation (Copy Button Added)
# ==========================================
def generate_dashboard(targets):
    action_group = [s for s in targets if s['rib_data']['grade'] in ['ACTION', 'SETUP']]
    radar_group = [s for s in targets if s['rib_data']['grade'] == 'RADAR']
    others_group = [s for s in targets if s['rib_data']['grade'] == 'IGNORE']

    def render_card(stock):
        sym = stock['symbol']
        rib = stock.get("rib_data")
        narr = stock.get("narrative", {})
        
        drop_html = ""
        for n in narr.get('drop_news', []):
            tag_color = "#c0392b" if n['type'] == 'risk' else "#e67e22"
            drop_html += f"<div class='news-item'><span class='news-tag' style='background:{tag_color}'>{n['category']}</span><a href='{n['link']}' target='_blank'>{n['title_ko']}</a></div>"
        if not drop_html: drop_html = "<div class='empty-msg'>📉 (뉴스 생략/부족)</div>"

        rec_html = ""
        for n in narr.get('recovery_news', []):
            tag_color = "#27ae60" if n['type'] == 'good' else "#7f8c8d"
            rec_html += f"<div class='news-item'><span class='news-tag' style='background:{tag_color}'>{n['category']}</span><a href='{n['link']}' target='_blank'>{n['title_ko']}</a></div>"
        if not rec_html: rec_html = "<div class='empty-msg'>🌱 (뉴스 생략/부족)</div>"

        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        grade = rib.get("grade", "N/A")
        grade_color = {"ACTION": "#e74c3c", "SETUP": "#e67e22", "RADAR": "#f1c40f", "IGNORE": "#95a5a6"}.get(grade, "#555")
        comps = rib.get("components", {})
        
        narr_score = narr.get('narrative_score', 0)
        status_label = narr.get('status_label', 'Unknown')
        narr_badge_color = "#555"
        if narr_score >= 60: narr_badge_color = "#27ae60" 
        elif narr_score >= 30: narr_badge_color = "#f39c12" 
        
        return f"""
        <div class="card">
            <div class="card-header">
                <span class="sym">{sym}</span>
                <span class="price">${stock.get('price',0)}</span>
                <span class="dd-badge">{stock.get('dd',0):.1f}%</span>
                <span class="narrative-badge" style="background:{narr_badge_color}">{status_label}</span>
            </div>
            <div class="card-body-grid">
                <div class="col-drop">
                    <div class="col-title">📉 DROP CAUSE</div>
                    {drop_html}
                </div>
                <div class="col-chart">
                    <div class="tradingview-widget-container">
                        <div id="{chart_id}" style="height:250px;"></div>
                        <script type="text/javascript">
                            new TradingView.widget({{
                                "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC", "theme": "dark", 
                                "style": "1", "locale": "en", "hide_top_toolbar": true, "hide_legend": true, 
                                "container_id": "{chart_id}",
                                "studies": ["MAExp@tv-basicstudies"],
                                "studies_overrides": {{ "MAExp@tv-basicstudies.length": 224, "MAExp@tv-basicstudies.plot.color": "#FFB000", "MAExp@tv-basicstudies.plot.linewidth": 5, "MAExp@tv-basicstudies.plot.transparency": 10 }}
                            }});
                        </script>
                    </div>
                    <div class="rib-stat-box" style="border-top: 3px solid {grade_color}">
                        <div class="rib-header">
                            <span style="color:{grade_color}; font-weight:bold;">{grade} : {rib.get('status')}</span>
                            <span>Score {rib.get('rib_score',0)}</span>
                        </div>
                        <div style="display:flex; gap:10px; margin-top:5px; font-size:0.75em; color:#aaa; justify-content:center;">
                            <span>📐{comps.get('struct',0)}</span>
                            <span>🗜️{comps.get('comp',0)}</span>
                            <span>🎯{comps.get('prox',0)}</span>
                            <span>🛡️{comps.get('risk',0)}</span>
                        </div>
                        <div class="rib-msg">💡 {rib.get('trigger_msg','')}</div>
                    </div>
                </div>
                <div class="col-rec">
                    <div class="col-title">🌱 RECOVERY SIGNAL</div>
                    {rec_html}
                </div>
            </div>
        </div>
        """

    # Group Symbols for Copy Button
    action_syms = ",".join([s['symbol'] for s in action_group])
    radar_syms = ",".join([s['symbol'] for s in radar_group])
    others_syms = ",".join([s['symbol'] for s in others_group])

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sniper V10.5 US Full Universe</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script>
            function copySymbols(text, btn) {{
                if (!text) return;
                navigator.clipboard.writeText(text).then(() => {{
                    const original = btn.innerText;
                    btn.innerText = "✅ Copied!";
                    setTimeout(() => btn.innerText = original, 2000);
                }});
                event.stopPropagation(); // Prevent detail toggle
            }}
        </script>
        <style>
            body {{ background: #131722; color: #d1d4dc; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ text-align: center; color: #e67e22; letter-spacing: 1px; margin-bottom: 30px; }}
            
            details {{ margin-bottom: 30px; background: #1e222d; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
            summary {{ padding: 15px; background: #2a2e39; cursor: pointer; font-weight: bold; font-size: 1.1em; display: flex; justify-content: space-between; align-items: center; }}
            summary:hover {{ background: #363c4e; }}
            
            .copy-btn {{ background: #3498db; color: white; border: none; padding: 5px 15px; border-radius: 4px; cursor: pointer; font-size: 0.8em; font-weight: bold; }}
            .copy-btn:hover {{ background: #2980b9; }}

            .section-content {{ padding: 20px; display: flex; flex-direction: column; gap: 20px; }}
            .card {{ background: #151924; border: 1px solid #2a2e39; border-radius: 8px; overflow: hidden; }}
            .card-header {{ padding: 12px 20px; background: #202533; border-bottom: 1px solid #2a2e39; display: flex; align-items: center; gap: 15px; }}
            .sym {{ font-size: 1.4em; font-weight: bold; color: #fff; }}
            .price {{ font-weight: bold; color: #fff; }}
            .dd-badge {{ background: #444; color: #ddd; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; }}
            .narrative-badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; color: #fff; }}

            .card-body-grid {{ display: grid; grid-template-columns: 1fr 1.2fr 1fr; height: 380px; }}
            .col-drop {{ border-right: 1px solid #2a2e39; padding: 15px; overflow-y: auto; background: rgba(192, 57, 43, 0.05); }}
            .col-chart {{ padding: 0; display: flex; flex-direction: column; }}
            .col-rec {{ border-left: 1px solid #2a2e39; padding: 15px; overflow-y: auto; background: rgba(39, 174, 96, 0.05); }}
            
            .col-title {{ font-size: 0.85em; font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px; color: #aaa; text-transform: uppercase; }}
            .news-item {{ margin-bottom: 8px; font-size: 0.85em; line-height: 1.4; }}
            .news-tag {{ color: #fff; padding: 1px 4px; border-radius: 3px; font-size: 0.75em; margin-right: 5px; }}
            .news-item a {{ color: #ccc; text-decoration: none; }}
            .news-item a:hover {{ color: #fff; text-decoration: underline; }}
            .empty-msg {{ font-style: italic; color: #555; font-size: 0.8em; margin-top: 20px; text-align: center; }}

            .rib-stat-box {{ background: #1e222d; padding: 10px; flex-grow: 1; display: flex; flex-direction: column; justify-content: center; }}
            .rib-header {{ display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.9em; }}
            .rib-msg {{ color: #e67e22; font-size: 0.85em; text-align: center; margin-top: 5px; font-style: italic; }}
            
            @media (max-width: 768px) {{ 
                .card-body-grid {{ grid-template-columns: 1fr; height: auto; }} 
                .col-drop, .col-rec {{ max-height: 200px; }}
                .tradingview-widget-container {{ height: 300px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V10.5 <span style="font-size:0.6em; color:#aaa;">US FULL UNIVERSE / COPY PIPELINE</span></h1>
            
            <div style="text-align:center; color:#777; margin-bottom:20px; font-size:0.9em;">
                ⚙️ Mode: US Market (Nasdaq/NYSE/Amex) | Batch Scan | Top Liquid + Random
            </div>
            
            <details open>
                <summary>
                    <span>🔥 ACTION & SETUP ({len(action_group)})</span>
                    <button class="copy-btn" onclick="copySymbols('{action_syms}', this)">📋 Copy Symbols</button>
                </summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in action_group]) if action_group else "<div style='text-align:center; color:#555;'>해당 없음</div>"}
                </div>
            </details>

            <details>
                <summary>
                    <span>📡 RADAR ({len(radar_group)})</span>
                    <button class="copy-btn" onclick="copySymbols('{radar_syms}', this)">📋 Copy Symbols</button>
                </summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in radar_group]) if radar_group else "<div style='text-align:center; color:#555;'>해당 없음</div>"}
                </div>
            </details>

            <details>
                <summary>
                    <span>💤 OTHERS ({len(others_group)})</span>
                    <button class="copy-btn" onclick="copySymbols('{others_syms}', this)">📋 Copy Symbols</button>
                </summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in others_group])}
                </div>
            </details>
        </div>
    </body>
    </html>
    """

    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

if __name__ == "__main__":
    print_status("🚀 Sniper Engine Started...")
    try:
        targets = run_scan()
        generate_dashboard(targets)
        print_status("✅ Workflow Complete.")
    except Exception as e:
        print_status(f"❌ Fatal Error: {e}")
        sys.exit(1)
