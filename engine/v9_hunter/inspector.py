import os
import json
import google.generativeai as genai
from datetime import datetime

class NewsInspector:
    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            # [수정] 가장 호환성 좋은 'gemini-pro' 모델 사용
            self.model = genai.GenerativeModel("gemini-pro")
        else:
            self.model = None

    def analyze(self, symbol, news_list):
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news data."}}

        # 뉴스 요약 (상위 3개만 - 속도 최적화)
        news_text = "\n".join([f"- {n['title']}" for n in news_list[:3]])

        if not self.model:
            return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "API Key Missing"}}

        # 프롬프트 (간결하게)
        prompt = f"""
        Analyze stock {symbol} based on news:
        {news_text}
        
        Output JSON only:
        {{
            "action": "WATCH" or "DISCARD",
            "score": 0-100,
            "risk": "LOW" or "MEDIUM" or "HIGH",
            "summary": "One short sentence reason."
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            # 텍스트 클리닝 (Markdown 제거)
            raw = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            
            return {
                "symbol": symbol,
                "action": data.get("action", "WATCH"),
                "reasoning_score": data.get("score", 50),
                "risk_level": data.get("risk", "MEDIUM"),
                "thesis": {"summary": data.get("summary", "AI Analysis Complete")},
                "last_updated": datetime.now().strftime("%H:%M")
            }
        except Exception as e:
            # 실패해도 뉴스 제목은 보여준다
            print(f"   ⚠️ AI Error on {symbol}: {e}")
            return {
                "symbol": symbol,
                "action": "WATCH",
                "reasoning_score": 0,
                "risk_level": "ERROR",
                "thesis": {"summary": f"News: {news_list[0]['title']}"}
            }
