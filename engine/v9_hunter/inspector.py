import os
import json
import requests
from datetime import datetime

class NewsInspector:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        # [수정] 사령관님 지시: -latest 접미사 추가 (활성 모델 강제 지정)
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"

    def analyze(self, symbol, news_list):
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news detected."}}

        if not self.api_key:
            return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "API Key Missing"}}

        # 뉴스 데이터 준비
        news_text = "\n".join([f"- {n['title']}" for n in news_list[:3]])

        # 요청 데이터 (JSON 구조)
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
                        "risk": "LOW" or "MEDIUM" or "HIGH",
                        "summary": "One concise sentence reason in Korean."
                    }}
                    """
                }]
            }]
        }

        try:
            # HTTP 요청 전송
            response = requests.post(
                f"{self.base_url}?key={self.api_key}",
                headers={"Content-Type": "application/json"},
                json=payload
            )
            
            # 응답 코드 확인
            if response.status_code != 200:
                print(f"   ⚠️ API Error {response.status_code}: {response.text[:100]}...")
                # 404가 또 뜨면 모델 리스트라도 보여주기 위해 에러 발생
                raise Exception(f"API Failed: {response.status_code}")

            # 응답 파싱
            result = response.json()
            try:
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
            except (KeyError, IndexError):
                # 모델은 응답했는데 내용이 비어있을 경우
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
                "thesis": {"summary": data.get("summary", f"News found: {news_list[0]['title']}")},
                "last_updated": datetime.now().strftime("%H:%M")
            }

        except Exception as e:
            # 최후의 수단: 에러가 나도 뉴스는 보여준다
            return {
                "symbol": symbol,
                "action": "WATCH",
                "reasoning_score": 10,
                "risk_level": "ERROR",
                "thesis": {"summary": f"News: {news_list[0]['title']}"}
            }
