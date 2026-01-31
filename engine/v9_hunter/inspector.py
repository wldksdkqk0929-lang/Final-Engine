import os
import json
import google.generativeai as genai
from datetime import datetime

class NewsInspector:
    def __init__(self):
        # API 키 설정
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-1.5-flash")
        else:
            self.model = None

    def analyze(self, symbol, news_list):
        # 1. 뉴스가 없으면 즉시 복귀
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news data available."}}

        # 2. 뉴스 데이터 텍스트화
        news_text = "\n".join([f"- {n['title']} ({n['published']})" for n in news_list[:5]])

        # 3. AI에게 물어보기
        if not self.model:
            return {"symbol": symbol, "action": "WATCH", "reasoning_score": 10, "risk_level": "LOW", "thesis": {"summary": f"System Alert: API Key missing. News found: {news_list[0]['title']}"}}

        prompt = f"""
        You are a Wall Street Sniper. Analyze the following news for {symbol}.
        
        [NEWS DATA]
        {news_text}
        
        [INSTRUCTIONS]
        1. Decide ACTION: 'WATCH' (if good news/momentum) or 'DISCARD' (if bad/boring).
        2. Score (0-100) based on catalyst strength.
        3. Risk: 'LOW', 'MEDIUM', 'HIGH'.
        4. Summary: One concise sentence explaining WHY. (Korean translation preferred if possible, else English).
        
        [OUTPUT FORMAT]
        Return ONLY valid JSON:
        {{
            "action": "WATCH" or "DISCARD",
            "score": 50,
            "risk": "MEDIUM",
            "summary": "Key reason..."
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            
            # JSON 파싱 (마크다운 제거)
            raw_text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw_text)
            
            return {
                "symbol": symbol,
                "action": data.get("action", "WATCH"),
                "reasoning_score": data.get("score", 0),
                "risk_level": data.get("risk", "MEDIUM"),
                "thesis": {
                    "summary": data.get("summary", f"Analysis complete based on {len(news_list)} articles.")
                },
                "last_updated": datetime.now().strftime("%H:%M")
            }
            
        except Exception as e:
            # 실패 시 비상 리포트 작성 (뉴스 제목이라도 보여주기)
            print(f"   ⚠️ Parsing Error on {symbol}: {e}")
            fallback_summary = f"AI Error, but News Detected: {news_list[0]['title']}"
            return {
                "symbol": symbol,
                "action": "WATCH", # 에러가 나도 뉴스가 있으면 일단 보여줌
                "reasoning_score": 10,
                "risk_level": "ERROR",
                "thesis": {"summary": fallback_summary}
            }
