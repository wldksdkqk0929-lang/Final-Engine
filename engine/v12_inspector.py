import json
import os
import requests
from datetime import datetime

# V12 스캐너가 찾아낸 타겟 파일 로드
try:
    with open("targets.json", "r") as f:
        TARGETS = json.load(f)
except FileNotFoundError:
    print("❌ No targets found. Run scanner first.")
    exit()

class V12Inspector:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model_endpoint = None

    def get_working_model(self):
        """작동하는 AI 모델 자동 탐색"""
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            response = requests.get(url)
            if response.status_code != 200: return None
            models = response.json().get("models", [])
            candidates = [m for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]
            
            for m in candidates:
                if "gemini-1.5-flash" in m["name"]: return m["name"]
            for m in candidates:
                if "gemini-pro" in m["name"]: return m["name"]
            return candidates[0]["name"] if candidates else None
        except:
            return None

    def analyze_target(self, target):
        symbol = target['symbol']
        status = target['status'] # OVERSOLD or VOL_SPIKE
        
        # 1. 뉴스 데이터 수집 (가상 함수 - 실제로는 구글 서치나 야후 파이낸스 크롤링 필요)
        # 현재는 V12 로직 테스트를 위해 AI에게 '최근 이슈를 아는 대로 말해라'고 지시
        
        if not self.model_endpoint:
            model_name = self.get_working_model()
            if model_name:
                self.model_endpoint = f"{self.base_url}/{model_name}:generateContent"
            else:
                return None

        # --- 🎯 V12 핵심 프롬프트 (함정 제거 & 반등 확인) ---
        prompt = f"""
        Analyze stock {symbol}.
        Context: It dropped {target['drawdown']}% from high, RSI is {target['rsi']}. It is technically OVERSOLD.
        
        Task 1 [Trap Check]: Are there any "Death Flags" like fraud, bankruptcy risk, or delisting warnings in recent 2 weeks?
        Task 2 [Catalyst Check]: Is there any specific news (insider buy, new product, earnings surprise) that could trigger a rebound?
        Task 3 [Hype Check]: Is the news already too optimistic (Too Late)?
        
        Output JSON ONLY:
        {{
            "action": "WATCH" (Safe to buy) or "DISCARD" (Dangerous),
            "risk_level": "LOW" or "HIGH",
            "korean_summary": "Write 1 sentence in Korean about the reason for drop and potential rebound.",
            "buying_catalyst": "Short keyword (e.g. Insider Buy)" or "None"
        }}
        """

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            response = requests.post(
                f"{self.model_endpoint}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            result = response.json()
            raw = result["candidates"][0]["content"]["parts"][0]["text"]
            clean = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean)
            
            # 기술적 데이터와 AI 분석 병합
            return {
                "symbol": symbol,
                "tech_data": target,
                "ai_analysis": data,
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
        except Exception as e:
            print(f"⚠️ Analysis failed for {symbol}: {e}")
            return None

    def run(self):
        final_report = []
        print(f"🕵️‍♂️ Inspector V12 Started. Analyzing {len(TARGETS)} candidates...")
        
        for target in TARGETS:
            print(f"   ... Inspecting {target['symbol']} (RSI: {target['rsi']})")
            result = self.analyze_target(target)
            if result:
                final_report.append(result)
        
        # 결과 저장
        with open("v12_report.json", "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=4, ensure_ascii=False)
        
        print(f"✅ Inspection Complete. Report saved to 'v12_report.json'")

if __name__ == "__main__":
    inspector = V12Inspector()
    inspector.run()
