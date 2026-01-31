import os
import json
import requests
from datetime import datetime

class NewsInspector:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model_endpoint = None # 나중에 자동으로 채워짐

    def get_working_model(self):
        """현재 API 키로 사용 가능한 모델을 자동으로 찾습니다."""
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            response = requests.get(url)
            
            if response.status_code != 200:
                print(f"   ⚠️ Failed to list models: {response.status_code}")
                return None
                
            models = response.json().get('models', [])
            
            # 1순위: 1.5-flash, 2순위: pro, 3순위: 아무 gemini 모델
            candidates = [m for m in models if 'generateContent' in m.get('supportedGenerationMethods', [])]
            
            # 우선순위 로직
            for m in candidates:
                if 'gemini-1.5-flash' in m['name']:
                    return m['name']
            for m in candidates:
                if 'gemini-pro' in m['name']:
                    return m['name']
            if candidates:
                return candidates[0]['name'] # 뭐라도 있으면 쓴다
                
            return None
        except Exception as e:
            print(f"   ⚠️ Auto-Discovery Error: {e}")
            return None

    def analyze(self, symbol, news_list):
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news."}}

        if not self.api_key:
            return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "API Key Missing"}}

        # [자동 탐색] 모델이 아직 설정 안 됐으면 찾기
        if not self.model_endpoint:
            model_name = self.get_working_model()
            if model_name:
                # model_name은 'models/gemini-1.5-flash-001' 형태임
                print(f"   🤖 Locked on Model: {model_name}")
                self.model_endpoint = f"{self.base_url}/{model_name}:generateContent"
            else:
                return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "No Available AI Model Found"}}

        news_text = "\n".join([f"- {n['title']}" for n in news_list[:3]])

        # 요청 데이터
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"""
                    Role: Analyst.
                    Task: Analyze news for {symbol}.
                    
                    NEWS:
                    {news_text}
                    
                    Output JSON ONLY:
                    {{
                        "action": "WATCH" or "DISCARD",
                        "score": 0-100,
                        "risk": "LOW" or "MEDIUM",
                        "summary": "One concise sentence reason in Korean."
                    }}
                    """
                }]
            }]
        }

        try:
            response = requests.post(
                f"{self.model_endpoint}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            
            if response.status_code != 200:
                print(f"   ⚠️ API Error {response.status_code}...")
                raise Exception("API Request Failed")

            result = response.json()
            try:
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
            except:
                raw_text = "{}"

            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            try:
                data = json.loads(clean_text)
            except:
                data = {}
            
            return {
                "symbol": symbol,
                "action": data.get("action", "WATCH"),
                "reasoning_score": data.get("score", 50),
                "risk_level": data.get("risk", "MEDIUM"),
                "thesis": {"summary": data.get("summary", f"News: {news_list[0]['title']}")},
                "last_updated": datetime.now().strftime("%H:%M")
            }

        except Exception as e:
            return {
                "symbol": symbol,
                "action": "WATCH",
                "reasoning_score": 10,
                "risk_level": "ERROR",
                "thesis": {"summary": f"Fallback: {news_list[0]['title']}"}
            }
