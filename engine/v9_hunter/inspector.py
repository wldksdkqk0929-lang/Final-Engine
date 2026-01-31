import os
import json
import requests
from datetime import datetime

class NewsInspector:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        # 구글 서버 직통 주소 (라이브러리 없이 직접 타격)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    def analyze(self, symbol, news_list):
        # 1. 뉴스가 없으면 복귀
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news detected."}}

        # 2. 키가 없으면 에러 처리
        if not self.api_key:
            return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "System Alert: API Key Missing"}}

        # 3. 뉴스 요약 (상위 3개)
        news_text = "\n".join([f"- {n['title']}" for n in news_list[:3]])

        # 4. 프롬프트 작성
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"""
                    Role: Wall Street Analyst.
                    Task: Analyze news for {symbol} and decide action.
                    
                    NEWS:
                    {news_text}
                    
                    Output JSON ONLY:
                    {{
                        "action": "WATCH" or "DISCARD",
                        "score": 0-100,
                        "risk": "LOW" or "MEDIUM" or "HIGH",
                        "summary": "One concise sentence reason in Korean(if possible) or English."
                    }}
                    """
                }]
            }]
        }

        try:
            # 5. 구글 서버로 직접 전송 (POST)
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            
            # 6. 응답 해석
            if response.status_code != 200:
                print(f"   ⚠️ API Error {response.status_code}: {response.text[:50]}...")
                raise Exception("API Request Failed")

            result = response.json()
            raw_text = result['candidates'][0]['content']['parts'][0]['text']
            
            # JSON 청소 (마크다운 제거)
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()
            data = json.loads(clean_text)
            
            return {
                "symbol": symbol,
                "action": data.get("action", "WATCH"),
                "reasoning_score": data.get("score", 50),
                "risk_level": data.get("risk", "MEDIUM"),
                "thesis": {"summary": data.get("summary", "Analysis Complete")},
                "last_updated": datetime.now().strftime("%H:%M")
            }

        except Exception as e:
            # 실패 시에도 뉴스 제목은 보여줌
            return {
                "symbol": symbol,
                "action": "WATCH",
                "reasoning_score": 10,
                "risk_level": "ERROR",
                "thesis": {"summary": f"News Found: {news_list[0]['title']}"}
            }
