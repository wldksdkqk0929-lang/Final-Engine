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

# ---------------------------------------------------------
# ⚙️ V10.1 설정 (Verification Config)
# ---------------------------------------------------------
UNIVERSE_MAX = 150
CUTOFF_SCORE = 65       # 최소 RIB 점수 (서사 분석 자격)
CUTOFF_DEEP_DROP = -55  # 고점 대비 하락률 제한
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
    print_status("🌐 [Universe] 거래소 리스트 다운로드 중...")
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
    print_status("🏗️ [Universe Builder] 유니버스 구축 시작...")
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
# 2. RIB V2 Engine (Structure Analysis)
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
# 3. Narrative Engine (V10.1 Fixed)
# ==========================================
def classify_news_semantics(title, context_type):
    title_lower = title.lower()
    
    if context_type == "DROP":
        if any(k in title_lower for k in ['fraud', 'investigation', 'sec probe', 'lawsuit', 'bankruptcy', 'delisting', 'scandal']):
            return "🔴 Structural Risk", "risk"
        if any(k in title_lower for k in ['miss', 'earnings', 'revenue', 'guidance', 'downgrade', 'cut', 'slumps']):
            return "📉 Event Shock", "event"
        if any(k in title_lower for k in ['fed', 'inflation', 'market', 'yield', 'sector']):
            return "🌍 Macro Noise", "macro"
        return "📉 Drop Factor", "event"

    elif context_type == "RECOVERY":
        if any(k in title_lower for k in ['upgrade', 'beat', 'raise', 'partnership', 'approval', 'record', 'buyback', 'jump', 'soar']):
            return "🟢 Recovery Signal", "good"
        if any(k in title_lower for k in ['fall', 'drop', 'cut', 'lawsuit']):
            return "⚠️ Risk Lingering", "bad"
        return "⚖️ General News", "neutral"
    
    return "News", "neutral"

def fetch_narrative_news(symbol, start_date, end_date, context_type):
    items = []
    try:
        query = f"{symbol} stock"
        if start_date: query += f" after:{start_date}"
        if end_date: query += f" before:{end_date}"
        
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=4)
        
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            translator = GoogleTranslator(source='auto', target='ko')
            
            # [HOTFIX] 안전을 위해 최대 5개로 확장하여 날짜 필터링 확률 증가
            for item in root.findall('./channel/item')[:5]: 
                title = item.find('title').text.rsplit(" - ", 1)[0]
                pubDate = item.find('pubDate').text[:16]
                link = item.find('link').text
                
                try: title_ko = translator.translate(title)
                except: title_ko = title
                
                cat_text, cat_type = classify_news_semantics(title, context_type)
                
                if context_type == "DROP" and cat_type == "macro":
                    continue 

                items.append({
                    "title": title, "title_ko": title_ko, "link": link, 
                    "date": pubDate, "category": cat_text, "type": cat_type
                })
    except: pass
    return items

def analyze_narrative_completeness(symbol, rib_data):
    # [HOTFIX] Crash 방지를 위한 기본값 정의
    empty_result = {
        "drop_news": [],
        "recovery_news": [],
        "is_complete": False,
        "status_label": "⚠️ Data Unavailable"
    }
    
    if not rib_data: return empty_result
    
    try:
        dt_a = datetime.strptime(rib_data['base_a_date'], "%Y-%m-%d")
        dt_b = datetime.strptime(rib_data['base_b_date'], "%Y-%m-%d")
        
        # [HOTFIX] Drop 기간 확장 (10일 -> 15일)
        drop_start = (dt_a - timedelta(days=15)).strftime("%Y-%m-%d")
        drop_end = (dt_a + timedelta(days=5)).strftime("%Y-%m-%d")
        
        rec_start = rib_data['base_b_date']
        
        drop_news = fetch_narrative_news(symbol, drop_start, drop_end, "DROP")
        rec_news = fetch_narrative_news(symbol, rec_start, None, "RECOVERY")
        
        has_drop_cause = len(drop_news) > 0
        has_recovery_signal = False
        
        for n in rec_news:
            if n['type'] == 'good': has_recovery_signal = True
        
        is_complete = has_drop_cause and has_recovery_signal
        
        return {
            "drop_news": drop_news,
            "recovery_news": rec_news,
            "is_complete": is_complete,
            "status_label": "✅ Narrative Complete" if is_complete else "⚠️ Narrative Incomplete"
        }
    except Exception as e:
        # 에러 발생 시에도 빈 구조체 반환하여 크래시 방지
        return empty_result

# ==========================================
# 4. Main Scan Logic
# ==========================================
def run_scan():
    print_status("🧠 [Brain] Turnaround Sniper V10.1 (Verified Engine) 가동...")
    
    universe = build_universe()
    survivors = []
    
    print(f"\n🔍 서사 기반 정밀 스캔 시작 ({len(universe)}개 종목)...")

    for i, sym in enumerate(universe):
        try:
            print(f"   Scanning [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            
            t = yf.Ticker(sym)
            hist = t.history(period="6mo")
            if len(hist) < 120: continue
            
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100
            
            if dd <= CUTOFF_DEEP_DROP: continue
            
            rib_data = analyze_reignition_structure(hist)
            if not rib_data: continue
            
            if rib_data['rib_score'] < CUTOFF_SCORE: continue

            narrative = analyze_narrative_completeness(sym, rib_data)
            
            survivors.append({
                "symbol": sym, "price": round(cur, 2), "dd": round(dd, 2),
                "name": t.info.get("shortName", sym),
                "rib_data": rib_data,
                "narrative": narrative
            })

        except: continue

    # [HOTFIX] 정렬 시 키 에러 방지를 위한 안전 접근
    survivors.sort(key=lambda x: (
        0 if x.get('narrative', {}).get('is_complete', False) else 1,
        x['rib_data'].get('priority', 99), 
        -x['rib_data'].get('rib_score', 0)
    ))
    
    print(f"\n✅ 최종 분석 완료: {len(survivors)}개 종목 보고")
    return survivors

# ==========================================
# 5. Dashboard Generation
# ==========================================
def generate_dashboard(targets):
    # 안전한 그룹 분리
    complete_group = [s for s in targets if s.get('narrative', {}).get('is_complete', False)]
    incomplete_group = [s for s in targets if not s.get('narrative', {}).get('is_complete', False)]

    def render_card(stock):
        sym = stock['symbol']
        rib = stock.get("rib_data")
        narr = stock.get("narrative", {})
        
        # Drop News
        drop_html = ""
        for n in narr.get('drop_news', []):
            tag_color = "#c0392b" if n['type'] == 'risk' else "#e67e22"
            drop_html += f"""
            <div class="news-item">
                <span class="news-date">{n['date']}</span>
                <span class="news-tag" style="background:{tag_color}">{n['category']}</span>
                <a href="{n['link']}" target="_blank">{n['title_ko']}</a>
            </div>
            """
        if not drop_html: drop_html = "<div class='empty-msg'>📉 과거 데이터 없음 (Google RSS 제한)</div>"

        # Recovery News
        rec_html = ""
        for n in narr.get('recovery_news', []):
            tag_color = "#27ae60" if n['type'] == 'good' else "#7f8c8d"
            rec_html += f"""
            <div class="news-item">
                <span class="news-date">{n['date']}</span>
                <span class="news-tag" style="background:{tag_color}">{n['category']}</span>
                <a href="{n['link']}" target="_blank">{n['title_ko']}</a>
            </div>
            """
        if not rec_html: rec_html = "<div class='empty-msg'>🌱 회복 뉴스 없음</div>"

        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        grade = rib.get("grade", "N/A")
        grade_color = {"ACTION": "#e74c3c", "SETUP": "#e67e22", "RADAR": "#f1c40f", "IGNORE": "#95a5a6"}.get(grade, "#555")
        
        comps = rib.get("components", {})
        
        rib_html = f"""
        <div class="rib-stat-box" style="border-top: 3px solid {grade_color}">
            <div class="rib-header">
                <span style="color:{grade_color}; font-weight:bold;">{grade}</span>
                <span style="color:#aaa;">Score {rib.get('rib_score',0)}</span>
            </div>
            <div class="rib-metrics">
                <span>Base A: ${rib.get('base_a',0):.2f}</span>
                <span>Base B: ${rib.get('base_b',0):.2f}</span>
            </div>
            <div style="display:flex; gap:5px; margin-top:8px; font-size:0.7em; color:#aaa; justify-content:center; background:#222; padding:3px; border-radius:3px;">
                <span title="Structure">📐{comps.get('struct',0)}</span>
                <span title="Compression">🗜️{comps.get('comp',0)}</span>
                <span title="Proximity">🎯{comps.get('prox',0)}</span>
                <span title="Risk">🛡️{comps.get('risk',0)}</span>
            </div>
            <div class="rib-msg">💡 {rib.get('trigger_msg','')}</div>
        </div>
        """

        is_complete = narr.get('is_complete', False)
        status_label = narr.get('status_label', 'Unknown')

        return f"""
        <div class="card">
            <div class="card-header">
                <span class="sym">{sym}</span>
                <span class="name">{stock.get('name','')}</span>
                <span class="price">${stock.get('price',0)}</span>
                <span class="dd-badge">{stock.get('dd',0):.1f}%</span>
                <span class="narrative-badge { 'complete' if is_complete else 'incomplete' }">{status_label}</span>
            </div>
            <div class="card-body-grid">
                <div class="col-drop">
                    <div class="col-title">📉 DROP CAUSE</div>
                    {drop_html}
                </div>
                <div class="col-chart">
                    <div class="tradingview-widget-container">
                        <div id="{chart_id}" style="height:200px;"></div>
                        <script type="text/javascript">
                            new TradingView.widget({{
                                "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC", "theme": "dark", 
                                "style": "1", "locale": "en", "hide_top_toolbar": true, "hide_legend": true, "container_id": "{chart_id}"
                            }});
                        </script>
                    </div>
                    {rib_html}
                </div>
                <div class="col-rec">
                    <div class="col-title">🌱 RECOVERY SIGNAL</div>
                    {rec_html}
                </div>
            </div>
        </div>
        """

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Sniper V10.1 Verified Engine</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <style>
            body {{ background: #131722; color: #d1d4dc; font-family: 'Segoe UI', sans-serif; padding: 20px; margin: 0; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            h1 {{ text-align: center; color: #e67e22; letter-spacing: 1px; margin-bottom: 30px; }}
            
            details {{ margin-bottom: 30px; background: #1e222d; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
            summary {{ padding: 15px; background: #2a2e39; cursor: pointer; font-weight: bold; font-size: 1.1em; }}
            summary:hover {{ background: #363c4e; }}
            
            .section-content {{ padding: 20px; display: flex; flex-direction: column; gap: 20px; }}
            
            .card {{ background: #151924; border: 1px solid #2a2e39; border-radius: 8px; overflow: hidden; }}
            .card-header {{ padding: 12px 20px; background: #202533; border-bottom: 1px solid #2a2e39; display: flex; align-items: center; gap: 15px; }}
            .sym {{ font-size: 1.4em; font-weight: bold; color: #fff; }}
            .name {{ font-size: 0.9em; color: #888; flex-grow: 1; }}
            .price {{ font-weight: bold; color: #fff; }}
            .dd-badge {{ background: #444; color: #ddd; padding: 2px 6px; border-radius: 4px; font-size: 0.8em; }}
            .narrative-badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
            .narrative-badge.complete {{ background: #27ae60; color: #fff; }}
            .narrative-badge.incomplete {{ background: #555; color: #aaa; }}

            .card-body-grid {{ display: grid; grid-template-columns: 1fr 1.2fr 1fr; height: 350px; }}
            
            .col-drop {{ border-right: 1px solid #2a2e39; padding: 15px; overflow-y: auto; background: rgba(192, 57, 43, 0.05); }}
            .col-chart {{ padding: 0; display: flex; flex-direction: column; }}
            .col-rec {{ border-left: 1px solid #2a2e39; padding: 15px; overflow-y: auto; background: rgba(39, 174, 96, 0.05); }}
            
            .col-title {{ font-size: 0.85em; font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px; color: #aaa; text-transform: uppercase; }}
            
            .news-item {{ margin-bottom: 8px; font-size: 0.85em; line-height: 1.4; }}
            .news-date {{ color: #666; font-size: 0.8em; margin-right: 5px; }}
            .news-tag {{ color: #fff; padding: 1px 4px; border-radius: 3px; font-size: 0.75em; margin-right: 5px; }}
            .news-item a {{ color: #ccc; text-decoration: none; }}
            .news-item a:hover {{ color: #fff; text-decoration: underline; }}
            .empty-msg {{ font-style: italic; color: #555; font-size: 0.8em; margin-top: 20px; text-align: center; }}

            .rib-stat-box {{ background: #1e222d; padding: 10px; flex-grow: 1; display: flex; flex-direction: column; justify-content: center; }}
            .rib-header {{ display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 0.9em; }}
            .rib-metrics {{ display: flex; justify-content: space-between; font-size: 0.8em; color: #ccc; margin-bottom: 5px; }}
            .rib-msg {{ color: #e67e22; font-size: 0.85em; text-align: center; margin-top: 5px; font-style: italic; }}

        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V10.1 <span style="font-size:0.6em; color:#aaa;">VERIFIED ENGINE</span></h1>
            
            <details open>
                <summary>✅ NARRATIVE COMPLETE ({len(complete_group)}) - 서사 완성 종목 (강력 추천)</summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in complete_group]) if complete_group else "<div style='text-align:center; color:#555;'>완벽한 서사 종목 없음</div>"}
                </div>
            </details>

            <details>
                <summary>⚠️ NARRATIVE INCOMPLETE ({len(incomplete_group)}) - 서사 부족 / 단순 반등</summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in incomplete_group])}
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
