import os
import json
import requests
from datetime import datetime

class NewsInspector:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        # [변경] 가장 범용적인 'gemini-pro' 모델 사용
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent"

    def analyze(self, symbol, news_list):
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news detected."}}

        if not self.api_key:
            return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "API Key Missing"}}

        news_text = "\n".join([f"- {n['title']}" for n in news_list[:3]])

        # Gemini Pro용 데이터 포맷
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"""
                    Role: Financial Analyst.
                    Task: Analyze news for {symbol}.
                    
                    NEWS:
                    {news_text}
                    
                    Output JSON ONLY:
                    {{
                        "action": "WATCH" or "DISCARD",
                        "score": 0-100,
                        "risk": "LOW" or "MEDIUM",
                        "summary": "One short sentence in Korean."
                    }}
                    """
                }]
            }]
        }

        try:
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            
            if response.status_code != 200:
                # 에러 발생 시 상세 내용 출력
                print(f"   ⚠️ API Error {response.status_code}: {response.text[:100]}...")
                raise Exception("API Request Failed")

            result = response.json()
            # 안전한 파싱
            try:
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
            except:
                raw_text = "{}"

            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            # JSON 파싱 시도 (실패시 빈 딕셔너리)
            try:
                data = json.loads(clean_text)
            except:
                data = {}
            
            return {
                "symbol": symbol,
                "action": data.get("action", "WATCH"),
                "reasoning_score": data.get("score", 50),
                "risk_level": data.get("risk", "MEDIUM"),
                "thesis": {"summary": data.get("summary", f"News found: {news_list[0]['title']}")},
                "last_updated": datetime.now().strftime("%H:%M")
            }

        except Exception as e:
            return {
                "symbol": symbol,
                "action": "WATCH",
                "reasoning_score": 10,
                "risk_level": "ERROR",
                "thesis": {"summary": f"News: {news_list[0]['title']}"}
            }
