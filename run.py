import sys
import subprocess
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

# ==========================================
# 1. 라이브러리 설정
# ==========================================
def install_and_import(package, pip_name=None):
    if pip_name is None: pip_name = package
    try:
        return __import__(package)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return __import__(package)

yf = install_and_import("yfinance")
requests = install_and_import("requests")
pd = install_and_import("pandas")
np = install_and_import("numpy")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
    from deep_translator import GoogleTranslator

# ETF 리스트
ETF_LIST = ["TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"]

# ==========================================
# 2. V8.6 핵심: 재점화 구조 엔진 + 전술 레이어
# ==========================================
def analyze_reignition_structure(hist):
    try:
        if len(hist) < 120: return None
        
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
        # 1. Base A 탐지
        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]
        base_a_date = base_a_idx.strftime("%Y-%m-%d")
        
        # Pivot 탐지
        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5: 
            return {"status": "FORMING_A", "score": 0, "grade": "IGNORE", "priority": 4}

        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]
        pivot_date = pivot_idx.strftime("%Y-%m-%d")
        
        if pivot_date == base_a_date:
             return {"status": "BOUNCING", "score": 10, "grade": "IGNORE", "priority": 4}

        # 2. Base B 탐지
        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3: 
             return {"status": "AT_PIVOT", "score": 20, "grade": "IGNORE", "priority": 4}

        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]
        base_b_date = base_b_idx.strftime("%Y-%m-%d")

        # 구조 무효화 조건
        if base_b_price < base_a_price:
            return {"status": "INVALID (Low Broken)", "score": 0, "grade": "IGNORE", "priority": 99}
        if current_price < base_b_price:
            return {"status": "INVALID (B Broken)", "score": 0, "grade": "IGNORE", "priority": 99}

        # [V8.6] 전술 등급 및 트리거 문구 생성
        if pivot_price == 0: dist_pct = 0
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        status = ""
        grade = ""
        badge_color = ""
        priority = 4
        trigger_msg = ""
        score = 50

        # Higher Low 보너스
        if base_b_price > base_a_price * 1.05: score += 10

        if current_price > pivot_price:
            status = "🔥 BREAKOUT"
            grade = "ACTION"
            badge_color = "#e74c3c" # Red
            priority = 1
            trigger_msg = "Pivot 돌파 확인. 눌림목(Pullback) 또는 분할 진입 검토."
            score += 40
        elif dist_pct <= 3.0:
            status = "🚀 READY"
            grade = "SETUP"
            badge_color = "#e67e22" # Orange
            priority = 2
            trigger_msg = f"Pivot까지 {dist_pct:.1f}% 남음. 장중 돌파 및 거래량 주시."
            score += 30
        elif dist_pct <= 8.0:
            status = "👀 WATCH"
            grade = "RADAR"
            badge_color = "#f1c40f" # Yellow
            priority = 3
            trigger_msg = f"구조 형성 중. Pivot 접근 여부 지속 관찰 (Gap {dist_pct:.1f}%)."
            score += 10
        else:
            status = "💤 EARLY"
            grade = "IGNORE"
            badge_color = "#95a5a6" # Grey
            priority = 4
            trigger_msg = "아직 이격도가 큼. 관망 필요."

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
            "score": score
        }

    except Exception as e:
        return None

# ==========================================
# 3. 뉴스 구조 분석 (V8.0 유지)
# ==========================================
def analyze_news_structure(title_en):
    title_lower = title_en.lower()
    tags = []
    structural_keywords = ['lawsuit', 'sec', 'probe', 'investigation', 'ban', 'fraud', 'scandal', 'breach', 'recall', 'ceo resign']
    oneoff_keywords = ['earnings', 'revenue', 'miss', 'estimate', 'downgrade', 'guidance', 'profit', 'weather']
    if any(k in title_lower for k in structural_keywords): tags.append(("🔴 구조적 리스크", "risk"))
    elif any(k in title_lower for k in oneoff_keywords): tags.append(("📉 실적/이벤트", "event"))
    else: tags.append(("⚖️ 일반 변동", "normal"))
    
    reg_keywords = ['fda', 'ftc', 'doj', 'biden', 'trump', 'regulation', 'antitrust', 'policy', 'tax']
    if any(k in title_lower for k in reg_keywords): tags.append(("🏛️ 규제/정책", "gov"))
    macro_keywords = ['fed', 'rate', 'inflation', 'cpi', 'jobs', 'sector', 'competitor', 'war', 'oil']
    if any(k in title_lower for k in macro_keywords): tags.append(("🌍 시장/매크로", "macro"))
    pending_keywords = ['may', 'could', 'potential', 'consider', 'talks', 'rumor', 'reportedly']
    if any(k in title_lower for k in pending_keywords): tags.append(("❓ 불확실/미확정", "pending"))
    return tags

# ==========================================
# 4. 메인 로직 (자동 정렬 추가)
# ==========================================
def check_hard_cut(ticker, hist):
    try:
        try: market_cap = ticker.fast_info['market_cap']
        except: market_cap = ticker.info.get("marketCap", 0) or 0
        avg_dollar_vol = (hist["Close"] * hist["Volume"]).rolling(20).mean().iloc[-1]
        if market_cap < 2_000_000_000: return False, "Small Cap"
        if avg_dollar_vol < 20_000_000: return False, "Low Liquidity"
        return True, "Pass"
    except: return False, "Data Error"

def calc_atr_and_tier(hist):
    high, low, close = hist["High"], hist["Low"], hist["Close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(20).mean().iloc[-1]
    cur_price = close.iloc[-1]
    if cur_price == 0: return 3, -35, 0, "Error"
    vol_ratio = atr / cur_price
    if vol_ratio < 0.025: return 1, -15, round(vol_ratio * 100, 2), "Tier 1 (Safe)"
    elif vol_ratio < 0.05: return 2, -25, round(vol_ratio * 100, 2), "Tier 2 (Growth)"
    else: return 3, -35, round(vol_ratio * 100, 2), "Tier 3 (Volatile)"

def check_event_radar(hist):
    try:
        cur_vol = hist["Volume"].iloc[-1]
        avg_vol = hist["Volume"].rolling(20).mean().iloc[-1]
        vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0
        prev_close = hist["Close"].iloc[-2]
        cur_close = hist["Close"].iloc[-1]
        price_change_pct = abs((cur_close - prev_close) / prev_close) * 100
        gap_pct = abs((hist["Open"].iloc[-1] - prev_close) / prev_close) * 100
        if vol_ratio >= 2.5 and (price_change_pct >= 4.0 or gap_pct >= 2.0):
            return True, round(vol_ratio, 2), round(price_change_pct, 2)
        return False, round(vol_ratio, 2), round(price_change_pct, 2)
    except: return False, 0, 0

def run_logic():
    print("🧠 [Brain] Hybrid Sniper V8.6 (Tactical Layer) 가동...")
    
    universe = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX", "TSLA", "NVDA", "AMD", "AVGO",
        "CRM", "ADBE", "INTC", "CSCO", "CMCSA", "PEP", "KO", "COST", "WMT", "DIS",
        "PLTR", "SOFI", "AFRM", "UPST", "OPEN", "LCID", "RIVN", "DKNG", "ROKU", "SQ",
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "CVNA", "U", "RBLX", "PATH", "AI",
        "IONQ", "JOBY", "ACHR", "HIMS", "ALIT",
        "TQQQ", "SQQQ", "SOXL", "SOXS", "TSLL", "NVDL", "LABU", "LABD"
    ]

    survivors = []
    stats = {"HardCut": 0, "NotEnoughDrop": 0, "NoEvent": 0, "Error": 0, "Pass": 0}

    print(f"🔍 총 {len(universe)}개 종목 분석 중...\n")

    for i, sym in enumerate(universe):
        try:
            print(f"   Running.. [{i+1}/{len(universe)}] {sym:<5}", end="\r")
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 120: 
                stats["Error"] += 1
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

            is_hit, vol_spike, move_pct = check_event_radar(hist)
            if not is_hit:
                stats["NoEvent"] += 1
                continue
            
            reignition_data = analyze_reignition_structure(hist)

            stats["Pass"] += 1
            is_etf = sym in ETF_LIST
            final_label = f"[ETF] {tier_label}" if is_etf else tier_label
            
            print(f"🎯 [HIT] {sym} 포착! ({final_label})")
            
            survivors.append({
                "symbol": sym,
                "price": round(cur, 2),
                "dd": round(dd, 2),
                "tier_label": final_label,
                "radar_msg": f"Vol {vol_spike}x / Move {move_pct}%",
                "name": t.info.get("shortName", sym),
                "reignition": reignition_data
            })

        except Exception as e:
            stats["Error"] += 1
            continue

    # [V8.6 핵심] 전술적 우선순위 정렬 (ACTION -> SETUP -> RADAR -> IGNORE -> Score순)
    # priority가 낮을수록(1) 상단, score가 높을수록 상단
    survivors.sort(key=lambda x: (
        x['reignition'].get('priority', 99) if x['reignition'] else 99, 
        -x['reignition'].get('score', 0) if x['reignition'] else 0
    ))
    
    print("\n" + "="*40)
    print(f"📊 [스캔 결과] 총 {len(universe)}개 중")
    print(f"   ✅ 최종 포착: {stats['Pass']}")
    print("="*40 + "\n")
    
    return survivors

# ==========================================
# 5. 뉴스 및 대시보드 (V8.6 전술 UI)
# ==========================================
def calculate_relevance_score(title_en):
    score = 0
    title_lower = title_en.lower()
    tier1 = ['sec', 'fda', 'approved', 'lawsuit', 'regulation', 'settlement', 'won', 'ban', 'earnings', 'revenue']
    for kw in tier1: 
        if kw in title_lower: score += 10
    return score

def get_google_news_rss_optimized(symbol):
    raw_news = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall('./channel/item')[:5]:
                title = item.find('title').text
                if " - " in title: title = title.rsplit(" - ", 1)[0]
                pubDate = item.find('pubDate').text
                try: date_str = datetime.strptime(pubDate[:16], "%a, %d %b %Y").strftime("%Y.%m.%d")
                except: date_str = ""
                tags = analyze_news_structure(title)
                raw_news.append({"title_en": title, "link": item.find('link').text, "date_str": date_str, "score": calculate_relevance_score(title), "tags": tags})
            raw_news.sort(key=lambda x: x['score'], reverse=True)
            top_news = raw_news[:2]
            translator = GoogleTranslator(source='auto', target='ko')
            for item in top_news:
                try: item['title_ko'] = translator.translate(item['title_en'])
                except: item['title_ko'] = item['title_en']
            return top_news
    except: return []
    return []

def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        reig = stock.get("reignition")
        
        structure_html = ""
        tm_html = ""
        
        if reig and isinstance(reig, dict) and "status" in reig:
            # [V8.6] 전술 등급 배지 & 트리거 문구
            grade = reig.get('grade', 'IGNORE')
            grade_color = "#95a5a6"
            if grade == "ACTION": grade_color = "#e74c3c"
            elif grade == "SETUP": grade_color = "#e67e22"
            elif grade == "RADAR": grade_color = "#f1c40f"
            
            status_badge = f"<span class='struct-badge' style='background:{grade_color}'>{grade} : {reig.get('status')}</span>"
            trigger_msg = reig.get('trigger_msg', '')
            
            trigger_html = ""
            if trigger_msg:
                trigger_html = f"<div class='trigger-msg'>💡 {trigger_msg}</div>"

            # 상세 수치
            base_a = reig.get('base_a', 0)
            pivot = reig.get('pivot', 0)
            base_b = reig.get('base_b', 0)
            
            if "INVALID" not in reig.get('status', 'INVALID'):
                structure_html = f"""
                <div class="structure-box {grade.lower()}">
                    <div class="struct-header">
                        <span class="struct-title">⚔️ Tactical Analysis</span>
                        {status_badge}
                    </div>
                    {trigger_html}
                    <div class="struct-metrics">
                        <div class="s-item">
                            <span class="lbl">Base A</span>
                            <span class="val">${base_a:.2f}</span>
                        </div>
                        <div class="s-arrow">➔</div>
                        <div class="s-item">
                            <span class="lbl">Pivot (High)</span>
                            <span class="val">${pivot:.2f}</span>
                        </div>
                        <div class="s-arrow">➔</div>
                        <div class="s-item">
                            <span class="lbl">Base B</span>
                            <span class="val">${base_b:.2f}</span>
                        </div>
                    </div>
                    <div class="struct-footer">
                        <span>Gap to Breakout: <strong>{reig.get('distance', 0):.1f}%</strong> (Score: {reig.get('score')})</span>
                    </div>
                </div>
                """
                
                def make_google_url(query, date_str):
                    try:
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        start = (dt - timedelta(days=2)).strftime("%m/%d/%Y")
                        end = (dt + timedelta(days=2)).strftime("%m/%d/%Y")
                        return f"https://www.google.com/search?q={sym}+stock+news&tbs=cdr:1,cd_min:{start},cd_max:{end}&tbm=nws"
                    except: return "#"
                
                crash_url = make_google_url(sym, reig.get('base_a_date', ''))
                rebound_url = make_google_url(sym, reig.get('base_b_date', ''))
                
                tm_html = f"""
                <div class="timemachine-box">
                    <div class="tm-item crash">
                        <span class="tm-label">🔴 Crash (A)</span>
                        <a href="{crash_url}" target="_blank" class="tm-btn">뉴스 ➜</a>
                    </div>
                    <div class="tm-item rebound">
                        <span class="tm-label">🟢 Confirm (B)</span>
                        <a href="{rebound_url}" target="_blank" class="tm-btn">뉴스 ➜</a>
                    </div>
                </div>
                """
            else:
                structure_html = f"""
                <div class="structure-box invalid">
                    <div class="struct-header">
                        <span class="struct-title">⚠️ 구조 미형성</span>
                        <span class="struct-badge" style="background:#7f8c8d">{reig.get('status')}</span>
                    </div>
                </div>
                """

        if sym == "NO-TARGETS":
            news_html = "<p class='no-news'>탐지된 종목이 없습니다.</p>"
        else:
            news_data = get_google_news_rss_optimized(sym)
            news_html = ""
            if news_data:
                for n in news_data:
                    tags_html = ""
                    for tag_text, tag_type in n['tags']:
                        color = "#7f8c8d"
                        if tag_type == "risk": color = "#c0392b"
                        elif tag_type == "event": color = "#e67e22"
                        elif tag_type == "gov": color = "#8e44ad"
                        elif tag_type == "macro": color = "#2980b9"
                        tags_html += f"<span class='news-tag' style='background:{color};'>{tag_text}</span>"
                    news_html += f"<div class='news-item'><span class='date'>{n['date_str']}</span><div class='tags-row'>{tags_html}</div><a href='{n['link']}' target='_blank'>{n['title_ko']}</a></div>"
            else:
                news_html = "<p class='no-news'>최근 주요 뉴스가 없습니다.</p>"

        tier_label = stock.get('tier_label', '')
        radar_msg = stock.get('radar_msg', '')
        is_etf = "[ETF]" in tier_label
        badge_bg = "#8e44ad" if is_etf else "#2c3e50"
        tier_badge = f"<span class='badge' style='background:{badge_bg}; color:#ecf0f1;'>{tier_label}</span>" if tier_label else ""
        radar_badge = f"<span class='badge' style='background:rgba(242, 54, 69, 0.15); color:#f23645;'>{radar_msg}</span>" if radar_msg else ""

        html_cards += f"""
        <div class="card">
            <div class="card-header">
                <div class="stock-info">
                    <span class="symbol">{sym}</span>
                    <span class="name">{stock.get('name', '')}</span>
                </div>
                <div class="stock-metrics">
                    <span class="price">${stock['price']:.2f}</span>
                    {tier_badge}
                    {radar_badge}
                </div>
            </div>
            <div class="card-body">
                <div class="left-section">
                    {structure_html}
                    <div class="news-section">
                        <h4>📰 최신 뉴스 & AI 태그</h4>
                        <div class="news-list">{news_html}</div>
                    </div>
                    {tm_html}
                </div>
                <div class="chart-section">
                    <div class="tradingview-widget-container" style="height:100%;width:100%">
                        <div id="{chart_id}" style="height:100%;width:100%"></div>
                        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                        <script type="text/javascript">
                        new TradingView.widget({{
                            "autosize": true, "symbol": "{sym}", "interval": "D", "timezone": "Etc/UTC",
                            "theme": "dark", "style": "1", "locale": "kr", "toolbar_bg": "#1e222d",
                            "enable_publishing": false, "hide_side_toolbar": false,
                            "container_id": "{chart_id}"
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
        <title>Hybrid Sniper V8.6 (Tactical Layer)</title>
        <style>
            :root {{
                --bg-color: #131722; --card-bg: #1e222d; --text-main: #d1d4dc;
                --text-sub: #787b86; --accent-red: #f23645; --accent-blue: #2962ff;
                --border-color: #2a2e39;
            }}
            body {{ font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif; background: var(--bg-color); color: var(--text-main); padding: 40px 20px; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; margin-bottom: 40px; color: #fff; letter-spacing: 2px; }}
            .card {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
            .card-header {{ padding: 20px; border-bottom: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; }}
            .symbol {{ font-size: 1.8em; font-weight: 700; color: #fff; margin-right: 10px; }}
            .name {{ color: var(--text-sub); font-size: 0.9em; }}
            .price {{ font-size: 1.5em; font-weight: 600; color: #fff; margin-right: 15px; }}
            .badge {{ padding: 5px 10px; border-radius: 4px; font-weight: bold; font-size: 0.8em; margin-left: 5px; border: 1px solid #444; }}
            
            .card-body {{ display: flex; flex-wrap: wrap; height: 600px; }}
            .left-section {{ flex: 1; min-width: 350px; padding: 20px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; }}
            
            /* Tactical Structure Box */
            .structure-box {{ background: #262b3e; border-radius: 6px; padding: 15px; margin-bottom: 15px; border: 1px solid #363c4e; }}
            .structure-box.action {{ border: 1px solid #e74c3c; background: rgba(231, 76, 60, 0.1); }}
            .structure-box.setup {{ border: 1px solid #e67e22; background: rgba(230, 126, 34, 0.1); }}
            .structure-box.invalid {{ opacity: 0.5; }}
            
            .struct-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }}
            .struct-title {{ font-size: 0.9em; font-weight: bold; color: #fff; }}
            .struct-badge {{ padding: 3px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; color: #fff; }}
            
            .trigger-msg {{ background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; font-size: 0.85em; color: #f1c40f; margin-bottom: 10px; border-left: 3px solid #f1c40f; line-height: 1.4; }}

            .struct-metrics {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 0.8em; }}
            .s-item {{ display: flex; flex-direction: column; align-items: center; }}
            .s-arrow {{ color: var(--text-sub); font-size: 1.2em; }}
            .s-item .lbl {{ color: var(--text-sub); margin-bottom: 2px; font-size: 0.8em; }}
            .s-item .val {{ color: #fff; font-weight: bold; }}
            .struct-footer {{ text-align: center; border-top: 1px solid #363c4e; padding-top: 8px; font-size: 0.85em; color: var(--text-main); }}

            .news-section {{ flex-grow: 1; overflow-y: auto; margin-bottom: 15px; }}
            .news-item {{ margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #2a2e39; }}
            .tags-row {{ margin-bottom: 5px; }}
            .news-tag {{ font-size: 0.7em; color: #fff; padding: 2px 6px; border-radius: 3px; margin-right: 5px; display: inline-block; font-weight: bold; }}
            .news-item a {{ color: var(--text-main); text-decoration: none; font-size: 0.9em; display: block; line-height: 1.4; }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            .date {{ font-size: 0.75em; color: var(--text-sub); display: block; margin-bottom: 2px; }}
            .no-news {{ color: var(--text-sub); font-style: italic; font-size: 0.9em; }}

            .timemachine-box {{ border-top: 1px solid var(--border-color); padding-top: 10px; display: flex; gap: 10px; }}
            .tm-item {{ flex: 1; display: flex; flex-direction: column; align-items: center; padding: 8px; border-radius: 6px; }}
            .tm-item.crash {{ background: rgba(242, 54, 69, 0.1); border: 1px solid rgba(242, 54, 69, 0.3); }}
            .tm-item.rebound {{ background: rgba(38, 166, 154, 0.1); border: 1px solid rgba(38, 166, 154, 0.3); }}
            .tm-label {{ font-size: 0.75em; font-weight: bold; margin-bottom: 4px; }}
            .tm-btn {{ background: #2a2e39; color: var(--text-main); padding: 4px 10px; border-radius: 4px; text-decoration: none; font-size: 0.75em; width: 80%; text-align: center; }}
            .tm-btn:hover {{ background: #fff; color: #000; }}

            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            @media (max-width: 768px) {{ .card-body {{ height: auto; }} .left-section {{ border-right: none; border-bottom: 1px solid var(--border-color); }} .chart-section {{ height: 400px; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>SNIPER V8.6 <span style="font-size:0.5em; color:#e74c3c;">TACTICAL</span></h1>
            {html_cards}
        </div>
    </body>
    </html>
    """
    
    os.makedirs("data/artifacts/dashboard", exist_ok=True)
    with open("data/artifacts/dashboard/index.html", "w", encoding="utf-8") as f:
        f.write(full_html)

if __name__ == "__main__":
    targets = run_logic()
    if not targets:
        print("💡 결과가 0개입니다. 더미 리포트를 생성합니다.")
        targets = [{"symbol": "NO-TARGETS", "price": 0.00, "dd": 0.00, "name": "탐지된 종목이 없습니다", "tier_label": "System Info", "radar_msg": "Universe scanned"}]
    generate_dashboard(targets)
    print(f"\n✅ V8.6 작전 완료.")
