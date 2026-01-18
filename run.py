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

# 설정값
UNIVERSE_MAX = 150  # 분석할 최대 종목 수 (속도/API 제한 고려)
LIQUIDITY_LOOKBACK = 10 # 유동성 확인용 데이터 조회 기간 (일)

# ETF 리스트 (기본 제외 대상이나, 별도 관리)
ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]
# 항상 포함할 핵심 감시 종목 (Core Watchlist)
CORE_WATCHLIST = [
    "DKNG", "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "ROKU", "SQ",
    "COIN", "MSTR", "CVNA", "U", "RBLX", "PATH", "AI", "IONQ", "HIMS"
]

# ==========================================
# 2. Universe Builder (자동 유니버스 생성)
# ==========================================
def fetch_nasdaq_symbols():
    """NASDAQ 및 Other Listed(NYSE 등) 심볼 가져오기"""
    symbols = set()
    urls = [
        "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
        "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
    ]
    
    print("🌐 [Universe] 거래소 리스트 다운로드 중...")
    for url in urls:
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                # 파이프(|)로 구분된 텍스트
                df = pd.read_csv(StringIO(resp.text), sep="|")
                # 불필요한 것 제거 (Test Issue, ETF 등)
                if 'Test Issue' in df.columns:
                    df = df[df['Test Issue'] == 'N']
                if 'ETF' in df.columns:
                    df = df[df['ETF'] == 'N']
                
                # 심볼 추출 및 클리닝
                # 워런트, 우선주 등 제외 (심볼 길이 4이하 권장 or 알파벳만)
                clean_syms = df['Symbol'].dropna().astype(str).tolist()
                for s in clean_syms:
                    if s.isalpha() and len(s) <= 4: # 4글자 이하 순수 티커만 (잡주/파생 제외)
                        symbols.add(s)
        except Exception as e:
            print(f"⚠️ [Universe] 리스트 다운로드 실패 ({url}): {e}")
            continue
    
    return list(symbols)

def build_universe():
    """유동성 기반 유니버스 구축"""
    print("\n🏗️ [Universe Builder] 유니버스 구축 시작...")
    
    # 1. 전체 후보군 수집
    candidates = fetch_nasdaq_symbols()
    
    # 만약 다운로드 실패시 기본 리스트 + Core 사용
    if len(candidates) < 10:
        print("⚠️ [Universe] 온라인 수집 실패. 기본 리스트 사용.")
        candidates = list(set(CORE_WATCHLIST + ["AAPL", "MSFT", "TSLA", "NVDA", "AMD"]))
    else:
        # Core Watchlist는 무조건 포함
        candidates = list(set(candidates + CORE_WATCHLIST))

    print(f"   📋 1차 후보군: {len(candidates)}개 심볼")
    
    # 2. 유동성 상위 컷 (Liquidity Cut)
    # yfinance 배치가 너무 많으면 에러나므로 청크로 분할 처리
    print(f"   ⚖️ 유동성 분석 중 (Target: Top {UNIVERSE_MAX})...")
    
    final_universe = []
    chunk_size = 500 # 500개씩 나눠서 조회
    liquidity_scores = []

    # 전체를 다 돌리기엔 시간이 걸리므로, 랜덤 샘플링 + Core
    # Core는 무조건 포함, 나머지는 랜덤으로 섞어서 앞부분만 체크 (API 절약)
    # 실전에서는 전체를 다 체크하는게 좋으나, GitHub Actions 시간 제한 고려
    scan_pool = list(set(candidates) - set(CORE_WATCHLIST))
    random.shuffle(scan_pool)
    scan_targets = CORE_WATCHLIST + scan_pool[:1000] # 최대 1000개 + Core만 검사

    for i in range(0, len(scan_targets), chunk_size):
        chunk = scan_targets[i:i+chunk_size]
        try:
            # 최근 5일치만 다운로드
            data = yf.download(chunk, period="5d", progress=False, group_by='ticker', threads=True)
            
            for sym in chunk:
                try:
                    # 단일 종목일 경우와 MultiIndex일 경우 처리
                    if len(chunk) == 1:
                        df = data
                    else:
                        df = data[sym]
                    
                    if df.empty: continue
                    
                    # 평균 거래대금 계산 (Close * Volume)
                    avg_dol_vol = (df['Close'] * df['Volume']).mean()
                    if pd.isna(avg_dol_vol): avg_dol_vol = 0
                    
                    liquidity_scores.append((sym, avg_dol_vol))
                except: continue
        except Exception as e:
            print(f"   ⚠️ Chunk download error: {e}")
            continue
        print(f"   Running.. {min(i+chunk_size, len(scan_targets))}/{len(scan_targets)} verified", end="\r")

    # 3. 정렬 및 자르기
    liquidity_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Core 종목은 유동성 낮아도 강제 생존 시킬 수 있으나, 여기선 유동성 컷에 맡김
    # 다만 상위 N개에 Core가 없다면? -> Core는 별도 추가 로직 필요하지만 일단 단순화
    
    top_n = liquidity_scores[:UNIVERSE_MAX]
    final_universe = [x[0] for x in top_n]
    
    # Core 종목 누락 확인 및 복구
    for core in CORE_WATCHLIST:
        if core not in final_universe:
            final_universe.append(core) # Core는 강제 추가
            
    final_universe = list(set(final_universe)) # 중복 제거
    
    print(f"\n✅ [Universe] 최종 확정: {len(final_universe)}개 종목 (Liquidity Top + Core)")
    return final_universe

# ==========================================
# 3. Re-Ignition Engine (V8.7 Logic)
# ==========================================
def analyze_reignition_structure(hist):
    try:
        if len(hist) < 120: return None
        
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
        # Base A
        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]
        base_a_date = base_a_idx.strftime("%Y-%m-%d")
        
        # Pivot
        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5: 
            return {"status": "FORMING_A", "rib_score": 0, "grade": "IGNORE", "priority": 4}

        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]
        pivot_date = pivot_idx.strftime("%Y-%m-%d")
        
        if pivot_date == base_a_date:
             return {"status": "BOUNCING", "rib_score": 10, "grade": "IGNORE", "priority": 4}

        # Base B
        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3: 
             return {"status": "AT_PIVOT", "rib_score": 20, "grade": "IGNORE", "priority": 4}

        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]
        base_b_date = base_b_idx.strftime("%Y-%m-%d")

        # Invalid Conditions
        if base_b_price < base_a_price:
            return {"status": "INVALID (Low Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}
        if current_price < base_b_price:
            return {"status": "INVALID (B Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}

        # Scoring & Grading
        if pivot_price == 0: dist_pct = 0
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        status = ""
        grade = ""
        priority = 4
        trigger_msg = ""
        rib_score = 50

        if base_b_price > base_a_price * 1.05: rib_score += 10 # Higher Low Bonus

        if current_price > pivot_price:
            status = "🔥 RIB BREAKOUT"
            grade = "ACTION"
            priority = 1
            trigger_msg = "Pivot 돌파 확인. 진입 검토."
            rib_score += 40
        elif dist_pct <= 3.0:
            status = "🚀 RIB READY"
            grade = "SETUP"
            priority = 2
            trigger_msg = f"Pivot까지 {dist_pct:.1f}% 남음."
            rib_score += 30
        elif dist_pct <= 8.0:
            status = "👀 RIB WATCH"
            grade = "RADAR"
            priority = 3
            trigger_msg = f"구조 관찰 중 (Gap {dist_pct:.1f}%)."
            rib_score += 10
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
            "rib_score": rib_score
        }
    except: return None

# ==========================================
# 4. News & Noise Control
# ==========================================
def analyze_news_structure(title_en):
    title_lower = title_en.lower()
    tags = []
    # Keywords
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
    """
    노이즈 점수 계산 (3점 이상이면 Low Quality)
    - Pending(불확실) 뉴스: +1
    - Macro(매크로)만 있고 종목 이슈 없음: +1
    - Normal(일반)만 있음: +1
    - 변동성 과다 (ATR비율 높음 - 여기서는 vol_ratio로 대체 추정): +1
    """
    noise_score = 0
    reasons = []
    
    # 뉴스 기반 노이즈
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
        
    if is_all_normal and news_items: # 뉴스가 있는데 다 별거 아님
        noise_score += 1
        reasons.append("NoIssues")

    # 기술적 노이즈 (변동성 과다)
    # Tier 3 수준(Volatile)이면 노이즈로 간주 가능
    if vol_ratio > 0.05: # ATR/Price > 5%
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
            # 번역 (Top 2)
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
# 5. Main Scan Logic
# ==========================================
def check_hard_cut(ticker, hist):
    # 유니버스 단계에서 이미 거름, 여기선 데이터 무결성만 체크
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
        
        # V8.7 Logic: Tier classification
        if vol_ratio < 0.025: return 1, -10, vol_ratio, "Tier 1"
        elif vol_ratio < 0.05: return 2, -20, vol_ratio, "Tier 2"
        else: return 3, -30, vol_ratio, "Tier 3"
    except: return 3, -30, 0, "Error"

def run_scan():
    print("🧠 [Brain] Turnaround Sniper V9.0 (Universe Expansion) 가동...")
    
    # 1. 유니버스 구축
    universe = build_universe()
    
    survivors = []
    stats = {"HardCut": 0, "NotEnoughDrop": 0, "Pass": 0}
    
    print(f"\n🔍 정밀 스캔 시작 ({len(universe)}개 종목)...")

    for i, sym in enumerate(universe):
        try:
            print(f"   Scanning [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            
            # yfinance 호출 (개별)
            t = yf.Ticker(sym)
            hist = t.history(period="6mo") # 6개월치만 (속도 최적화)
            
            if len(hist) < 120:
                stats["HardCut"] += 1
                continue
                
            # 기초 체력 (이미 유동성 컷 했으므로 데이터 확인만)
            passed, reason = check_hard_cut(t, hist)
            if not passed:
                stats["HardCut"] += 1
                continue

            # 낙폭 & Tier
            tier, drop_limit, vol_ratio, tier_label = calc_atr_and_tier(hist)
            high_120 = hist["High"].rolling(120).max().iloc[-1]
            cur = hist["Close"].iloc[-1]
            dd = ((cur - high_120) / high_120) * 100

            if dd > drop_limit:
                stats["NotEnoughDrop"] += 1
                continue

            # RIB 구조 분석
            rib_data = analyze_reignition_structure(hist)
            
            # 뉴스 분석 & 노이즈 스코어
            news_items = get_google_news_rss(sym)
            noise_score, noise_reason = calculate_noise_score(news_items, vol_ratio)

            # Event Radar (Hard/Soft) - 간소화
            # V9.0에서는 RIB 구조가 중요하므로 Radar는 정보 제공용
            cur_vol = hist["Volume"].iloc[-1]
            avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
            vol_spike = round(cur_vol/avg_vol, 1) if avg_vol > 0 else 0
            
            stats["Pass"] += 1
            
            survivors.append({
                "symbol": sym,
                "price": round(cur, 2),
                "dd": round(dd, 2),
                "tier_label": tier_label,
                "radar_msg": f"Vol {vol_spike}x",
                "name": t.info.get("shortName", sym),
                "rib_data": rib_data,
                "news": news_items,
                "noise_score": noise_score,
                "noise_reason": noise_reason
            })
            
        except Exception as e:
            # print(f"Err: {sym} {e}")
            continue

    # 정렬: Priority(Action/Setup) -> Score(High) -> Noise(Low)
    survivors.sort(key=lambda x: (
        x['rib_data'].get('priority', 99) if x['rib_data'] else 99, 
        -x['rib_data'].get('rib_score', 0) if x['rib_data'] else 0,
        x['noise_score']
    ))
    
    print("\n" + "="*40)
    print(f"📊 [스캔 결과] 총 {len(universe)}개 중")
    print(f"   ❌ 탈락: {stats['HardCut'] + stats['NotEnoughDrop']}")
    print(f"   ✅ 최종 분석: {len(survivors)}")
    print("="*40 + "\n")
    
    return survivors

# ==========================================
# 6. Dashboard Generation (Display Tiers)
# ==========================================
def generate_dashboard(targets):
    # 그룹 분류
    top_tier = []
    mid_tier = []
    low_tier = []
    
    for s in targets:
        rib = s.get("rib_data")
        noise = s.get("noise_score", 0)
        
        # 분류 로직
        if rib and rib['grade'] == 'ACTION':
            top_tier.append(s)
        elif rib and rib['grade'] == 'SETUP' and noise < 2:
            top_tier.append(s)
        elif rib and rib['grade'] == 'RADAR' and noise < 3:
            mid_tier.append(s)
        else:
            low_tier.append(s) # IGNORE, INVALID, High Noise

    def render_card(stock):
        sym = stock['symbol']
        rib = stock.get("rib_data")
        noise_sc = stock.get("noise_score")
        noise_rs = stock.get("noise_reason")
        
        # RIB UI
        rib_html = ""
        if rib and "status" in rib:
            grade_color = {"ACTION": "#e74c3c", "SETUP": "#e67e22", "RADAR": "#f1c40f", "IGNORE": "#95a5a6"}.get(rib['grade'], "#95a5a6")
            rib_html = f"""
            <div class="rib-box" style="border-left: 4px solid {grade_color}; background: #262b3e; padding: 10px; margin-bottom: 10px; border-radius: 4px;">
                <div style="display:flex; justify-content:space-between; color:#fff; font-weight:bold; font-size:0.9em;">
                    <span>{rib['grade']} : {rib['status']}</span>
                    <span>Score: {rib['rib_score']}</span>
                </div>
                <div style="color:#d1d4dc; font-size:0.8em; margin-top:5px; display:flex; justify-content:space-between;">
                    <span>A: ${rib['base_a']:.2f} ➔ P: ${rib['pivot']:.2f} ➔ B: ${rib['base_b']:.2f}</span>
                    <span>Gap: {rib['distance']:.1f}%</span>
                </div>
                <div style="font-size:0.8em; color:#f1c40f; margin-top:5px;">💡 {rib['trigger_msg']}</div>
            </div>
            """
        
        # Noise UI
        noise_html = ""
        if noise_sc > 0:
            noise_html = f"<div style='font-size:0.75em; color:#7f8c8d; margin-bottom:5px;'>⚠️ Noise Lv.{noise_sc} ({noise_rs})</div>"

        # News UI
        news_html = ""
        for n in stock.get('news', []):
            tags_html = "".join([f"<span style='font-size:0.7em; background:#444; color:#fff; padding:1px 4px; border-radius:3px; margin-right:3px;'>{t[0]}</span>" for t in n['tags']])
            news_html += f"<div style='margin-bottom:4px;'><span style='font-size:0.7em; color:#aaa;'>{n['date_str']}</span> {tags_html} <a href='{n['link']}' target='_blank' style='color:#d1d4dc; font-size:0.85em; text-decoration:none;'>{n['title_ko']}</a></div>"
        if not news_html: news_html = "<div style='font-size:0.8em; color:#666;'>No recent news</div>"

        # TimeMachine Link
        tm_link = ""
        if rib and rib.get('base_b_date'):
            tm_link = f"<a href='https://www.google.com/search?q={sym}+stock+news+after:{rib['base_a_date']}+before:{rib['base_b_date']}' target='_blank' style='display:block; text-align:center; background:#2a2e39; color:#aaa; font-size:0.75em; padding:4px; margin-top:5px; text-decoration:none; border-radius:3px;'>🕒 TimeMachine Check</a>"

        chart_id = f"tv_{sym}_{random.randint(1000,9999)}"
        
        return f"""
        <div class="card">
            <div class="card-header">
                <span class="sym">{sym}</span> <span class="name">{stock['name']}</span>
                <span class="price">${stock['price']}</span>
                <span class="badge" style="background:#333;">{stock['tier_label']}</span>
                <span class="badge" style="background:#444;">{stock['dd']:.1f}%</span>
            </div>
            <div class="card-body">
                <div class="info-col">
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
                                "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC", "theme": "dark", "style": "1", "locale": "en", "toolbar_bg": "#f1f3f6", "enable_publishing": false, "hide_top_toolbar": true, "container_id": "{chart_id}"
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
        <title>Sniper V9.0 Universe</title>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <style>
            body {{ background: #131722; color: #d1d4dc; font-family: sans-serif; padding: 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; color: #e67e22; }}
            details {{ margin-bottom: 20px; background: #1e222d; border-radius: 8px; overflow: hidden; }}
            summary {{ padding: 15px; background: #2a2e39; cursor: pointer; font-weight: bold; list-style: none; }}
            summary:hover {{ background: #363c4e; }}
            .section-content {{ padding: 15px; display: grid; grid-template-columns: repeat(auto-fill, minmax(500px, 1fr)); gap: 15px; }}
            .card {{ background: #1e222d; border: 1px solid #2a2e39; border-radius: 6px; overflow: hidden; }}
            .card-header {{ padding: 10px; background: #262b3e; border-bottom: 1px solid #2a2e39; display: flex; align-items: center; gap: 10px; }}
            .sym {{ font-size: 1.2em; font-weight: bold; color: #fff; }}
            .name {{ font-size: 0.8em; color: #777; flex-grow: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
            .badge {{ font-size: 0.7em; padding: 2px 5px; border-radius: 3px; }}
            .card-body {{ display: flex; height: 300px; }}
            .info-col {{ flex: 4; padding: 10px; overflow-y: auto; border-right: 1px solid #2a2e39; }}
            .chart-col {{ flex: 6; }}
            .news-box {{ margin-top: 10px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V9.0 <span style="font-size:0.6em; color:#aaa;">UNIVERSE EXPANSION</span></h1>
            
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
                <summary>💤 LOW TIER (Ignore & Noise) - {len(low_tier)} Targets</summary>
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

if __name__ == "__main__":
    targets = run_scan()
    generate_dashboard(targets)
