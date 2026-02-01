import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# 1. 타겟 로드
try:
    with open("targets.json", "r") as f:
        TARGETS = json.load(f)
except:
    print("⚠️ No targets.json found.")
    TARGETS = []

API_KEY = os.environ.get("GEMINI_API_KEY")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# 2. [핵심] 모델 자동 탐색 함수 (이게 있어야 연결됨)
def get_working_model():
    try:
        url = f"{BASE_URL}/models?key={API_KEY}"
        response = requests.get(url)
        if response.status_code != 200: return None
        
        models = response.json().get('models', [])
        candidates = [m for m in models if 'generateContent' in m.get('supportedGenerationMethods', [])]
        
        # 우선순위: Flash -> Pro -> 아무거나
        for m in candidates:
            if 'gemini-1.5-flash' in m['name']: return m['name']
        for m in candidates:
            if 'gemini-pro' in m['name']: return m['name']
        if candidates: return candidates[0]['name']
        return None
    except:
        return None

# 3. 구글 뉴스 RSS 수집
def get_news(symbol):
    try:
        url = f"https://news.google.com/rss/search?q={symbol}+stock+news+after:2024-01-01&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        root = ET.fromstring(response.content)
        items = root.findall('.//item')
        return [f"- {item.find('title').text}" for item in items[:3]]
    except Exception as e:
        print(f"   ⚠️ RSS Error: {e}")
        return []

# 4. 심문 시작
def interrogate(target, model_name):
    symbol = target['symbol']
    news = get_news(symbol)
    
    if not news:
        print(f"   😶 {symbol}: No news found.")
        return None

    print(f"   🕵️ {symbol}: Analyzing {len(news)} articles...")
    news_text = "\n".join(news)
    
    # AI 프롬프트
    prompt = f"""
    Analyze {symbol} stock based on these headlines:
    {news_text}
    
    Context: Price dropped {target['drawdown']}% from high. Volume spiked {target['vol_ratio']}%.
    
    Output JSON ONLY:
    {{
        "status": "TRAP" (if bankruptcy/fraud/delisting),
        "status": "STRONG" (if insider buy/turnaround),
        "status": "LATE" (if hype),
        "status": "WATCH" (default),
        "reason_kr": "Short Korean summary.",
        "risk_level": "HIGH/MED/LOW"
    }}
    """
    
    url = f"{BASE_URL}/{model_name}:generateContent?key={API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        res = requests.post(url, json=payload)
        if res.status_code != 200:
            print(f"   ⚠️ AI Error {res.status_code}: {res.text[:50]}")
            return None
            
        raw = res.json()['candidates'][0]['content']['parts'][0]['text']
        clean = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(clean)
        
        # 중복 키 방지 및 병합
        if "status" not in data: data["status"] = "WATCH"
        target.update(data)
        return target
    except Exception as e:
        print(f"   ⚠️ Parsing Error: {e}")
        return None

# --- 실행 로직 ---
print(f"🚀 V12 Engine Started. Targets: {len(TARGETS)}")

# 모델 찾기
model = get_working_model()
if not model:
    print("❌ CRITICAL: No AI Model found via API.")
    exit()
print(f"🤖 Brain Connected: {model}")

final_report = []
for t in TARGETS:
    res = interrogate(t, model)
    if res:
        print(f"   ✅ [{res.get('status')}] {t['symbol']}: {res.get('reason_kr')}")
        final_report.append(res)

print(f"📋 Final Survivors: {len(final_report)}")

# 결과 저장
with open("final_v12_report.json", "w", encoding='utf-8') as f:
    json.dump(final_report, f, ensure_ascii=False, indent=4)
