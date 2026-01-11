import sys
import subprocess
import os
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

# ==========================================
# 1. 라이브러리 강제 설치 (Self-Healing)
# ==========================================
def install_and_import(package, pip_name=None):
    if pip_name is None:
        pip_name = package
    try:
        return __import__(package)
    except ImportError:
        print(f"📦 {pip_name} 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
        return __import__(package)

yf = install_and_import("yfinance")
requests = install_and_import("requests")
yaml = install_and_import("yaml")

# [핵심] 안정적인 번역기 (Deep Translator)
try:
    from deep_translator import GoogleTranslator
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "deep-translator"])
    from deep_translator import GoogleTranslator

# ==========================================
# 2. 로직: 낙폭 과대주 선별 (Brain)
# ==========================================
def run_logic():
    print("🧠 [Brain] 낙폭 과대주 분석 엔진 가동...")
    
    # 분석 대상 유니버스
    universe = [
        "MARA", "LCID", "TSLA", "INTC", "PLTR", "SOFI", "AMD", "NVDA", 
        "RIVN", "OPEN", "IONQ", "JOBY", "UPST", "AFRM", "COIN", "MSTR", "CVNA"
    ]
    
    survivors = []
    print(f"🔍 {len(universe)}개 종목 정밀 스캔 중...")
    
    for sym in universe:
        try:
            t = yf.Ticker(sym)
            hist = t.history(period="1y")
            if len(hist) < 20: continue
            
            high = hist['High'].max()
            cur = hist['Close'].iloc[-1]
            dd = ((cur - high) / high) * 100
            
            # [조건] 고점 대비 -40% 이상 하락
            if dd < -40:
                survivors.append({
                    "symbol": sym,
                    "price": cur,
                    "dd": round(dd, 2),
                    "name": t.info.get('shortName', sym)
                })
        except:
            continue
            
    # 낙폭 큰 순서로 정렬
    survivors.sort(key=lambda x: x['dd'])
    print(f"⚔️ 최종 생존 종목: {len(survivors)}개")
    return survivors

# ==========================================
# 3. 뉴스 엔진: 중요도 가중치 정렬 (NEW 🚀)
# ==========================================
def calculate_relevance_score(title_en):
    """
    제목에 '턴어라운드 핵심 키워드'가 있으면 점수를 높게 부여합니다.
    """
    score = 0
    title_lower = title_en.lower()
    
    # 1티어: 규제, 승인, 소송 결과 (가장 중요)
    tier1_keywords = ['sec', 'fda', 'approved', 'dismissed', 'lawsuit', 'regulation', 'settlement', 'won', 'cleared', 'ban']
    for kw in tier1_keywords:
        if kw in title_lower:
            score += 10
            
    # 2티어: 실적, 급등락 (차선)
    tier2_keywords = ['earnings', 'revenue', 'profit', 'surge', 'jump', 'plunge', 'crash', 'record', 'upgrade', 'downgrade']
    for kw in tier2_keywords:
        if kw in title_lower:
            score += 5
            
    return score

def get_google_news_rss_optimized(symbol):
    print(f"📰 {symbol} 뉴스 수집 및 중요도 분석 중...")
    raw_news_items = []
    
    try:
        # RSS 요청 (기본적으로 구글은 '관련도 순'으로 줍니다)
        url = f"https://news.google.com/rss/search?q={symbol}+stock&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            items = root.findall('./channel/item')
            
            # 데이터 가공
            for item in items:
                title = item.find('title').text
                if " - " in title: title = title.rsplit(" - ", 1)[0]
                
                pubDate = item.find('pubDate').text
                try:
                    dt_obj = datetime.strptime(pubDate[:16], "%a, %d %b %Y")
                    date_str = dt_obj.strftime("%Y.%m.%d")
                except:
                    date_str = ""
                
                # [핵심] 중요도 점수 계산
                score = calculate_relevance_score(title)

                raw_news_items.append({
                    "title_en": title,
                    "link": item.find('link').text,
                    "date_str": date_str,
                    "score": score  # 점수 저장
                })
            
            # [정렬 로직] 1순위: 중요도 점수(내림차순), 2순위: 원래 구글 순서
            raw_news_items.sort(key=lambda x: x['score'], reverse=True)
            
            # 상위 3개 추출
            top_news = raw_news_items[:3]
            
            # 번역 실행 (Deep Translator)
            translator = GoogleTranslator(source='auto', target='ko')
            final_items = []
            
            for item in top_news:
                try:
                    # 중요 키워드가 있어서 점수가 높으면 제목 앞에 [★] 표시
                    prefix = "★ " if item['score'] >= 10 else ""
                    
                    translated = translator.translate(item['title_en'])
                    item['title_ko'] = prefix + translated
                except:
                    item['title_ko'] = item['title_en']
                final_items.append(item)
                
            return final_items

    except Exception as e:
        print(f"⚠️ {symbol} 뉴스 처리 오류: {e}")
        return []
    
    return []

# ==========================================
# 4. 시각화: V6.5 터미널 (디자인 유지)
# ==========================================
def generate_dashboard(targets):
    html_cards = ""
    
    for stock in targets:
        sym = stock['symbol']
        chart_id = f"tv_{sym}"
        
        news_data = get_google_news_rss_optimized(sym)
        
        news_html = ""
        if news_data:
            for n in news_data:
                # 툴팁에 영어 원문 표시
                news_html += f"""
                <div class='news-item'>
                    <span class='date'>{n['date_str']}</span>
                    <a href='{n['link']}' target='_blank' title='[원문] {n['title_en']}'>
                        {n['title_ko']}
                    </a>
                </div>
                """
        else:
            news_html = "<p class='no-news'>관련 주요 뉴스가 없습니다.</p>"

        google_search_url = f"https://www.google.com/search?q={sym}+주식+뉴스&tbm=nws"
        news_footer = f"""
        <div class="news-footer">
            <a href="{google_search_url}" target="_blank" class="google-btn">
                구글 뉴스 더보기 ➜
            </a>
        </div>
        """

        html_cards += f"""
        <div class="card">
            <div class="card-header">
                <div class="stock-info">
                    <span class="symbol">{sym}</span>
                    <span class="name">{stock.get('name', '')}</span>
                </div>
                <div class="stock-metrics">
                    <span class="price">${stock['price']:.2f}</span>
                    <span class="badge">{stock['dd']}%</span>
                </div>
            </div>
            <div class="card-body">
                <div class="news-section">
                    <h4>📰 주요 뉴스 (AI 중요도 분석)</h4>
                    <div class="news-list">
                        {news_html}
                    </div>
                    {news_footer}
                </div>
                <div class="chart-section">
                    <div class="tradingview-widget-container" style="height:100%;width:100%">
                        <div id="{chart_id}" style="height:400px;width:100%"></div>
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
        <title>Sniper Dark Terminal KR</title>
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
            .badge {{ background: rgba(242, 54, 69, 0.15); color: var(--accent-red); padding: 5px 10px; border-radius: 4px; font-weight: bold; }}
            .card-body {{ display: flex; flex-wrap: wrap; height: 450px; }}
            .news-section {{ flex: 1; min-width: 300px; padding: 20px; border-right: 1px solid var(--border-color); display: flex; flex-direction: column; background: #1e222d; }}
            .news-list {{ flex-grow: 1; overflow-y: auto; }}
            .news-item {{ margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }}
            .news-item:last-child {{ border-bottom: none; }}
            .news-item a {{ color: var(--text-main); text-decoration: none; font-size: 0.95em; display: block; margin-top: 4px; line-height: 1.4; }}
            .news-item a:hover {{ color: var(--accent-blue); }}
            .date {{ font-size: 0.75em; color: var(--text-sub); display: block; margin-bottom: 4px; }}
            .no-news {{ color: var(--text-sub); font-style: italic; }}
            .news-footer {{ padding-top: 15px; border-top: 1px solid var(--border-color); text-align: center; }}
            .google-btn {{ background: #2a2e39; color: #fff; padding: 8px 16px; border-radius: 20px; text-decoration: none; font-size: 0.85em; transition: 0.3s; display: inline-block; }}
            .google-btn:hover {{ background: var(--accent-blue); }}
            .chart-section {{ flex: 2; min-width: 400px; height: 100%; }}
            @media (max-width: 768px) {{ .card-body {{ height: auto; }} .news-section {{ border-right: none; border-bottom: 1px solid var(--border-color); }} .chart-section {{ height: 400px; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>TURNAROUND SNIPER <span style="font-size:0.5em; color:#777;">V6.5 KR</span></h1>
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
        print("⚠️ 스캔된 종목이 없습니다.")
        targets = [{"symbol": "MARA", "price": 0.00, "dd": 0.00, "name": "No Targets Found"}]
    generate_dashboard(targets)
