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
    "gate3_dd_pass": 0,
    "rib_final_pass": 0,
    "news_scanned": 0,
    "start_time": time.time(),
    "end_time": 0
}

# ---------------------------------------------------------
# ⚙️ V11.5 설정 (News Detail Upgrade)
# ---------------------------------------------------------
TARGET_LIQUID_COUNT = 1200
FINAL_UNIVERSE_SIZE = 800
G1_MIN_PRICE = 5.0
G1_MIN_DOL_VOL = 8_000_000
G2_MIN_DD_60 = -6.0
G2_MAX_REC_60 = 0.98
G3_MAX_DD_252 = -12.0
CUTOFF_SCORE = 40

ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD", "UVXY", "SPY", "QQQ", "IWM"]
CORE_WATCHLIST = [
    "DKNG", "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "ROKU", "SQ",
    "COIN", "MSTR", "CVNA", "U", "RBLX", "PATH", "AI", "IONQ", "HIMS"
]

# ==========================================
# 1. Universe Builder
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
    candidates = fetch_us_market_symbols()
    candidates = list(set(candidates + CORE_WATCHLIST))
    print_status(f"   📋 Raw Pool: {len(candidates)}개 -> 유동성 타겟 {TARGET_LIQUID_COUNT}개 확보 시작")
    
    scan_pool = list(set(candidates) - set(CORE_WATCHLIST))
    random.shuffle(scan_pool)
    liquidity_scores = []
    
    # Core Scan
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

    # Pool Scan Loop
    chunk_size = 200
    pool_idx = 0
    while len(liquidity_scores) < TARGET_LIQUID_COUNT and pool_idx < len(scan_pool):
        chunk = scan_pool[pool_idx : pool_idx + chunk_size]
        pool_idx += chunk_size
        if not chunk: break
        try:
            data = yf.download(chunk, period="5d", group_by='ticker', threads=True, progress=False)
            if isinstance(data.columns, pd.MultiIndex):
                valid_cols = set(data.columns.get_level_values(0))
                for sym in chunk:
                    if sym in valid_cols:
                        df = data[sym]
                        if not df.empty:
                            avg = (df['Close'] * df['Volume']).mean()
                            if pd.isna(avg): avg = 0
                            liquidity_scores.append((sym, avg))
            else:
                if not data.empty and len(chunk) == 1:
                    avg = (data['Close'] * data['Volume']).mean()
                    liquidity_scores.append((chunk[0], avg))
        except: continue
        print(f"   ⚖️ Secured: {len(liquidity_scores)} / {TARGET_LIQUID_COUNT} (Scanned {pool_idx})", end="\r")

    liquidity_scores.sort(key=lambda x: x[1], reverse=True)
    top_600 = [x[0] for x in liquidity_scores[:600]]
    next_pool = [x[0] for x in liquidity_scores[600:1200]]
    random_200 = random.sample(next_pool, 200) if len(next_pool) > 200 else next_pool
        
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
            present_tickers = []
            if isinstance(data.columns, pd.MultiIndex): present_tickers = set(data.columns.get_level_values(0))
            elif not data.empty: present_tickers = batch 
            
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
            if isinstance(data.columns, pd.MultiIndex): present_tickers = set(data.columns.get_level_values(0))
            iter_list = batch if isinstance(data.columns, pd.MultiIndex) else ([batch[0]] if len(batch)==1 else [])

            for sym in iter_list:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if sym not in present_tickers: continue
                        df = data[sym].copy().dropna()
                    else: df = data.copy().dropna()

                    if len(df) < 40: continue
                    high_60 = df['High'].max()
                    cur_price = df['Close'].iloc[-1]
                    if high_60 == 0: continue
                    dd_60 = ((cur_price - high_60) / high_60) * 100
                    rec_ratio = cur_price / high_60
                    if dd_60 <= G2_MIN_DD_60 or rec_ratio <= G2_MAX_REC_60:
                        survivors.append(sym)
                except: continue
        except: continue
    PIPELINE_STATS["gate2_pass"] = len(survivors)
    print(f"   ➡️ Gate 2 Passed: {len(survivors)}")
    return survivors

# ==========================================
# 3. RIB V2 & Advanced News Engine (V11.5)
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
        
        if base_b_price < base_a_price * 0.98: return None 
        if current_price < base_b_price: return None
        
        score = 0
        ratio = base_b_price / base_a_price
        if 1.03 <= ratio <= 1.15: score += 30
        else: score += 10
        
        if pivot_price == 0: dist_pct = 99
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        if current_price > pivot_price: score += 25
        elif dist_pct <= 5.0: score += 20
        elif dist_pct <= 15.0: score += 10
        
        atr = (recent['High'] - recent['Low']).tail(14).mean()
        if (atr/current_price) < 0.05: score += 20
        
        if current_price > pivot_price: grade = "ACTION"
        elif dist_pct <= 8.0: grade = "SETUP"
        elif dist_pct <= 20.0: grade = "RADAR"
        else: grade = "IGNORE"
        
        comps = {"struct": int(ratio*10), "comp": 10, "prox": int(30-dist_pct), "risk": 10}
        
        pre_base_a = hist.loc[:base_a_idx]
        if not pre_base_a.empty:
            peak_idx = pre_base_a["High"].tail(252).idxmax()
            peak_date = peak_idx.strftime("%Y-%m-%d")
        else:
            peak_date = (base_a_idx - timedelta(days=60)).strftime("%Y-%m-%d")

        return {
            "grade": grade, "rib_score": score, 
            "base_a": base_a_price, "base_a_date": base_a_idx.strftime("%Y-%m-%d"),
            "base_b": base_b_price, "base_b_date": base_b_idx.strftime("%Y-%m-%d"),
            "pivot": pivot_price, "peak_date": peak_date,
            "trigger_msg": f"Gap {dist_pct:.1f}%", "components": comps
        }
    except: return None

# [News Logic - V11.5 Detail Upgrade]
def translate_cached(text, translator):
    if text in TRANSLATION_CACHE: return TRANSLATION_CACHE[text]
    try:
        res = translator.translate(text)
        TRANSLATION_CACHE[text] = res
        return res
    except: return text

def classify_news(title, n_type):
    t_low = title.lower()
    if n_type == "DROP":
        if any(k in t_low for k in ['fraud', 'sec', 'probe', 'lawsuit', 'delist', 'scandal']): return "🔴 Structural Risk", "risk", 30
        if any(k in t_low for k in ['miss', 'earnings', 'revenue', 'guidance', 'cut', 'plunge']): return "📉 Event Shock", "event", 20
        return "📉 Drop Factor", "event", 10
    else:
        if any(k in t_low for k in ['upgrade', 'beat', 'raise', 'partnership', 'record', 'soar']): return "🟢 Recovery Signal", "good", 30
        if any(k in t_low for k in ['fall', 'drop', 'cut', 'sell']): return "⚠️ Lingering Risk", "bad", -10
        return "⚖️ General", "neutral", 0

def fetch_news(symbol, start, end, n_type):
    items = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=3) # Strict timeout
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            translator = GoogleTranslator(source='auto', target='ko')
            t_start = datetime.strptime(start, "%Y-%m-%d")
            t_end = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
            
            count = 0
            for item in root.findall('./channel/item')[:20]:
                try:
                    pDateStr = item.find('pubDate').text
                    pDate = datetime.strptime(pDateStr[:16], "%a, %d %b %Y")
                    # Date Filter
                    if not (t_start <= pDate <= t_end + timedelta(days=1)): continue
                    
                    title_en = item.find('title').text.rsplit(" - ", 1)[0]
                    link = item.find('link').text
                    
                    if any(x['title_en'] == title_en for x in items): continue
                    
                    title_ko = translate_cached(title_en, translator)
                    cat, c_type, w = classify_news(title_en, n_type)
                    
                    items.append({
                        "published_date": pDate.strftime("%Y-%m-%d"),
                        "title_en": title_en,
                        "title_ko": title_ko,
                        "link": link,
                        "category": cat, 
                        "type": c_type, 
                        "weight": w
                    })
                    count += 1
                    if count >= 3: break # Max 3 per type
                except: continue
                
            # Sort by date
            # DROP: Oldest first (to see root cause)
            # RECOVERY: Newest first (to see latest signal)
            if n_type == "DROP":
                items.sort(key=lambda x: x['published_date'])
            else:
                items.sort(key=lambda x: x['published_date'], reverse=True)
                
    except: pass
    return items

def analyze_narrative(symbol, rib_data):
    # [Target Lock] Only scan Final Survivors
    if rib_data['rib_score'] < CUTOFF_SCORE:
        return {"narrative_score": 0, "status_label": "Low Score", "drop_news": [], "recovery_news": []}
    
    PIPELINE_STATS["news_scanned"] += 1
    try:
        # Drop News: Peak -> Base A + 10d
        drop_end = (datetime.strptime(rib_data['base_a_date'], "%Y-%m-%d") + timedelta(days=10)).strftime("%Y-%m-%d")
        d_news = fetch_news(symbol, rib_data['peak_date'], drop_end, "DROP")
        
        # Recovery News: Base B -> Now
        r_news = fetch_news(symbol, rib_data['base_b_date'], None, "RECOVERY")
        
        d_score = sum(n['weight'] for n in d_news)
        r_score = sum(n['weight'] for n in r_news)
        total = min(50, d_score) + min(50, r_score)
        
        lbl = f"Narrative {total}"
        return {"narrative_score": int(total), "status_label": lbl, "drop_news": d_news, "recovery_news": r_news}
    except: 
        return {"narrative_score": 0, "status_label": "Error", "drop_news": [], "recovery_news": []}

# ==========================================
# 4. Final Pipeline
# ==========================================
def apply_gate_3_and_rib(universe):
    print_status("🛡️ [Gate 3 & RIB] Deep Analysis (1Y Data)...")
    survivors = []
    batch_size = 50 
    for i in range(0, len(universe), batch_size):
        batch = universe[i:i+batch_size]
        try:
            data = yf.download(batch, period="1y", group_by='ticker', threads=True, progress=False)
            present_tickers = set()
            if isinstance(data.columns, pd.MultiIndex): present_tickers = set(data.columns.get_level_values(0))
            iter_list = batch if isinstance(data.columns, pd.MultiIndex) else ([batch[0]] if len(batch)==1 else [])

            for sym in iter_list:
                try:
                    if isinstance(data.columns, pd.MultiIndex):
                        if sym not in present_tickers: continue
                        df = data[sym].copy().dropna()
                    else: df = data.copy().dropna()
                    
                    if len(df) < 200: continue 
                    high_252 = df['High'].max()
                    cur = df['Close'].iloc[-1]
                    dd_252 = ((cur - high_252) / high_252) * 100
                    
                    if dd_252 > G3_MAX_DD_252: continue 
                    PIPELINE_STATS["gate3_dd_pass"] += 1
                    
                    rib_data = analyze_rib_structure(df)
                    if not rib_data: continue
                    if rib_data['rib_score'] < CUTOFF_SCORE: continue
                    PIPELINE_STATS["rib_final_pass"] += 1
                    
                    # News Engine Called Here
                    narr = analyze_narrative(sym, rib_data)
                    
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
# 5. Dashboard Generation (V11.5 Detail Upgrade)
# ==========================================
def generate_dashboard(targets):
    action = [s for s in targets if s['rib_data']['grade'] in ['ACTION', 'SETUP']]
    radar = [s for s in targets if s['rib_data']['grade'] == 'RADAR']
    others_group = [s for s in targets if s['rib_data']['grade'] == 'IGNORE']

    def render_card(stock):
        sym = stock['symbol']
        rib = stock.get("rib_data")
        narr = stock.get("narrative", {})
        
        # [UI Upgrade] Stacked News Display
        drop_html = ""
        if narr.get('drop_news'):
            for n in narr['drop_news']:
                tag_c = "#c0392b" if n['type'] == 'risk' else "#e67e22"
                drop_html += f"""
                <div class='news-item'>
                    <div class='news-meta'>
                        <span class='news-date'>{n['published_date']}</span>
                        <span class='news-tag' style='background:{tag_c}'>{n['category']}</span>
                    </div>
                    <div class='news-title-en'>{n['title_en']}</div>
                    <div class='news-title-ko'><a href='{n['link']}' target='_blank'>{n['title_ko']}</a></div>
                </div>
                """
        else: drop_html = "<div class='empty-msg'>📉 No significant drop news found</div>"

        rec_html = ""
        if narr.get('recovery_news'):
            for n in narr['recovery_news']:
                tag_c = "#27ae60" if n['type'] == 'good' else "#7f8c8d"
                rec_html += f"""
                <div class='news-item'>
                    <div class='news-meta'>
                        <span class='news-date'>{n['published_date']}</span>
                        <span class='news-tag' style='background:{tag_c}'>{n['category']}</span>
                    </div>
                    <div class='news-title-en'>{n['title_en']}</div>
                    <div class='news-title-ko'><a href='{n['link']}' target='_blank'>{n['title_ko']}</a></div>
                </div>
                """
        else: rec_html = "<div class='empty-msg'>🌱 No significant recovery news found</div>"

        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        grade = rib.get("grade", "N/A")
        grade_color = {"ACTION": "#e74c3c", "SETUP": "#e67e22", "RADAR": "#f1c40f", "IGNORE": "#95a5a6"}.get(grade, "#555")
        comps = rib.get("components", {})
        
        return f"""
        <div class="card">
            <div class="card-header">
                <div class="header-left">
                    <span class="sym">{sym}</span>
                    <span class="price">${stock.get('price',0)}</span>
                </div>
                <div class="header-right">
                    <span class="badge" style="background:{grade_color}">{grade}</span>
                    <span class="badge">Score {rib.get('rib_score',0)}</span>
                </div>
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
                                "studies_overrides": {{ "MAExp@tv-basicstudies.length": 224, "MAExp@tv-basicstudies.plot.color": "#FFB000", "MAExp@tv-basicstudies.plot.linewidth": 5 }}
                            }});
                        </script>
                    </div>
                    <div class="rib-stat-box" style="border-top: 2px solid {grade_color}">
                        <div style="display:flex; justify-content:space-between; font-size:0.8em; color:#aaa; margin-bottom:5px;">
                            <span>Base A: ${rib.get('base_a',0):.2f}</span>
                            <span>Base B: ${rib.get('base_b',0):.2f}</span>
                        </div>
                        <div style="display:flex; gap:8px; font-size:0.75em; color:#ddd; justify-content:center; background:#222; padding:4px; border-radius:4px;">
                            <span>📐St:{comps.get('struct',0)}</span>
                            <span>🗜️Cp:{comps.get('comp',0)}</span>
                            <span>🎯Px:{comps.get('prox',0)}</span>
                            <span>🛡️Rk:{comps.get('risk',0)}</span>
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

    action_syms = ",".join([s['symbol'] for s in action])
    radar_syms = ",".join([s['symbol'] for s in radar])
    others_syms = ",".join([s['symbol'] for s in others_group])

    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SNIPER V11.5 News Detail</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script>
            function copySymbols(text, btn) {{
                if (!text) return;
                navigator.clipboard.writeText(text).then(() => {{
                    const original = btn.innerText;
                    btn.innerText = "✅ Copied!";
                    setTimeout(() => btn.innerText = original, 2000);
                }});
                event.stopPropagation();
            }}
        </script>
        <style>
            :root {{ --bg-color: #131722; --card-bg: #1e222d; --border-color: #2a2e39; --text-main: #d1d4dc; --text-sub: #777; --accent: #e67e22; }}
            body {{ background: var(--bg-color); color: var(--text-main); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, "Open Sans", "Helvetica Neue", sans-serif; padding: 20px; margin: 0; }}
            .container {{ max-width: 1400px; margin: 0 auto; }}
            
            h1 {{ text-align: center; color: var(--accent); letter-spacing: 1px; margin-bottom: 20px; font-size: 1.8rem; }}
            .stats-bar {{ background: var(--border-color); padding: 10px; border-radius: 6px; text-align: center; margin-bottom: 20px; font-family: monospace; font-size: 0.9rem; color: #aaa; overflow-x: auto; white-space: nowrap; }}
            
            details {{ margin-bottom: 20px; background: var(--card-bg); border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.3); border: 1px solid var(--border-color); }}
            summary {{ padding: 15px 20px; background: var(--border-color); cursor: pointer; font-weight: bold; font-size: 1.1rem; display: flex; justify-content: space-between; align-items: center; user-select: none; }}
            summary:hover {{ background: #363c4e; }}
            
            .copy-btn {{ background: #2980b9; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.8rem; font-weight: bold; transition: background 0.2s; }}
            .copy-btn:hover {{ background: #3498db; }}

            .section-content {{ padding: 20px; display: flex; flex-direction: column; gap: 20px; }}
            
            .card {{ background: #151924; border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }}
            .card-header {{ padding: 12px 15px; background: #202533; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }}
            .header-left {{ display: flex; align-items: baseline; gap: 10px; }}
            .header-right {{ display: flex; align-items: center; gap: 8px; }}
            
            .sym {{ font-size: 1.3rem; font-weight: 800; color: #fff; }}
            .price {{ font-size: 1rem; font-weight: bold; color: #ddd; }}
            .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; color: #fff; background: #444; }}

            /* 3-Column Grid Layout */
            .card-body-grid {{ display: grid; grid-template-columns: 1fr 1.4fr 1fr; height: 400px; }}
            
            .col-drop {{ border-right: 1px solid var(--border-color); padding: 15px; overflow-y: auto; background: rgba(192, 57, 43, 0.05); }}
            .col-chart {{ padding: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border-color); }}
            .col-rec {{ padding: 15px; overflow-y: auto; background: rgba(39, 174, 96, 0.05); }}
            
            .col-title {{ font-size: 0.8rem; font-weight: bold; margin-bottom: 15px; border-bottom: 1px solid #444; padding-bottom: 5px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
            
            /* News Item Styling */
            .news-item {{ margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #2a2e39; }}
            .news-item:last-child {{ border-bottom: none; }}
            .news-meta {{ display: flex; align-items: center; margin-bottom: 4px; font-size: 0.75rem; color: #888; }}
            .news-date {{ margin-right: 8px; }}
            .news-tag {{ padding: 2px 6px; border-radius: 3px; font-size: 0.7rem; color: #fff; font-weight: bold; }}
            .news-title-en {{ font-size: 0.85rem; color: #aaa; margin-bottom: 2px; line-height: 1.2; font-style: italic; }}
            .news-title-ko a {{ font-size: 0.9rem; color: #ddd; font-weight: bold; text-decoration: none; line-height: 1.3; display: block; }}
            .news-title-ko a:hover {{ color: #fff; text-decoration: underline; color: var(--accent); }}
            .empty-msg {{ font-style: italic; color: #555; font-size: 0.8rem; text-align: center; margin-top: 30px; }}

            .rib-stat-box {{ background: var(--card-bg); padding: 10px; flex-grow: 1; display: flex; flex-direction: column; justify-content: center; }}
            .rib-msg {{ color: var(--accent); font-size: 0.9rem; text-align: center; margin-top: 8px; font-style: italic; font-weight: bold; }}
            
            /* Mobile Responsive */
            @media (max-width: 768px) {{ 
                .container {{ padding: 10px; }}
                h1 {{ font-size: 1.5rem; }}
                .stats-bar {{ font-size: 0.8rem; overflow-x: scroll; }}
                .card-body-grid {{ grid-template-columns: 1fr; height: auto; display: block; }}
                .col-drop, .col-rec {{ height: auto; max-height: 200px; border-right: none; border-bottom: 1px solid var(--border-color); }}
                .col-chart {{ border-right: none; border-bottom: 1px solid var(--border-color); }}
                .tradingview-widget-container {{ height: 250px; }}
                .rib-stat-box {{ padding: 15px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V11.5 <span style="font-size:0.6em; color:#777;">NEWS DETAIL UPGRADE</span></h1>
            
            <div class="stats-bar">
                Target: {PIPELINE_STATS['universe_target']} | Actual: {PIPELINE_STATS['universe_actual']} | 
                G1: {PIPELINE_STATS['gate1_pass']} | G2: {PIPELINE_STATS['gate2_pass']} | 
                DD: {PIPELINE_STATS['gate3_dd_pass']} | RIB: {PIPELINE_STATS['rib_final_pass']} |
                News: {PIPELINE_STATS['news_scanned']}
            </div>
            
            <details open>
                <summary>
                    <span>🔥 ACTION & SETUP ({len(action)})</span>
                    <button class="copy-btn" onclick="copySymbols('{action_syms}', this)">📋 Copy</button>
                </summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in action]) if action else "<div style='text-align:center; color:#555; padding:20px;'>No Targets Found</div>"}
                </div>
            </details>

            <details>
                <summary>
                    <span>📡 RADAR ({len(radar)})</span>
                    <button class="copy-btn" onclick="copySymbols('{radar_syms}', this)">📋 Copy</button>
                </summary>
                <div class="section-content">
                    {"".join([render_card(s) for s in radar]) if radar else "<div style='text-align:center; color:#555; padding:20px;'>No Targets Found</div>"}
                </div>
            </details>

            <details>
                <summary>
                    <span>💤 OTHERS ({len(others_group)})</span>
                    <button class="copy-btn" onclick="copySymbols('{others_syms}', this)">📋 Copy</button>
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

# ==========================================
# 6. Main Execution Block
# ==========================================
if __name__ == "__main__":
    try:
        print_status("🚀 SNIPER V11.5 News Detail Upgrade Start...")
        
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
