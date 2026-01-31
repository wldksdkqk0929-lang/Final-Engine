import os
import json
import re
import google.generativeai as genai

class NewsInspector:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            print("❌ [Inspector] Critical Error: GEMINI_API_KEY not found.")
            self.model = None
        else:
            genai.configure(api_key=self.api_key)
            # [FIX] 최신 모델 장착: gemini-2.0-flash
            self.model = genai.GenerativeModel('gemini-2.0-flash')

    def _clean_json_text(self, text):
        """LLM 응답에서 순수 JSON 부분만 추출"""
        try:
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```', '', text)
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != -1:
                return text[start:end]
            return text
        except:
            return text

    def analyze(self, symbol: str, news_list: list) -> dict:
        if not news_list:
            return {
                "symbol": symbol,
                "reasoning_score": 0,
                "risk_level": "UNKNOWN",
                "action": "DISCARD",
                "thesis_summary": "No news found."
            }

        if not self.model:
            return {
                "symbol": symbol,
                "reasoning_score": 0,
                "risk_level": "ERROR",
                "action": "DISCARD",
                "thesis_summary": "API Key Missing."
            }

        news_text = "\n".join([f"- [{n['published']}] {n['title']}" for n in news_list])
        
        # 프롬프트: AI에게 뉴스 분석 요청
        prompt = f"""
        Role: You are a professional cynical market analyst (The Hunter).
        Task: Analyze the recent news for {symbol} and decide if it's a valid turnaround entry target.
        
        [News Data]
        {news_text}
        
        [Evaluation Logic]
        1. Ignore generic noise or ad-like articles.
        2. Look for CLEAR turnaround signals: Earnings Beat, Guidance Raise, New Contract.
        3. Identify Fatal Risks: Fraud, Delisting, Bankruptcy.
        
        [Output Format]
        Provide the result strictly in JSON format:
        {{
            "reasoning_score": <int 0-100>,
            "risk_level": "LOW" | "MEDIUM" | "HIGH",
            "action": "ENGAGE" | "WATCH" | "DISCARD",
            "thesis_summary": "<One short sentence explaining why>"
        }}
        
        * Rules for 'action':
        - ENGAGE: Score > 75 AND Risk == LOW (Must have clear good news)
        - WATCH: Score 40-75 (Ambiguous or mixed)
        - DISCARD: Score < 40 OR Risk == HIGH (Bad news)
        """

        try:
            # 실제 API 호출
            response = self.model.generate_content(prompt)
            
            cleaned_text = self._clean_json_text(response.text)
            result = json.loads(cleaned_text)
            
            result["symbol"] = symbol
            return result

        except Exception as e:
            return {
                "symbol": symbol,
                "reasoning_score": 0,
                "risk_level": "ERROR",
                "action": "WATCH",
                "thesis_summary": f"Analysis failed: {str(e)}"
            }

if __name__ == "__main__":
    inspector = NewsInspector()
    dummy_news = [{"published": "2026-02-01", "title": "Tesla announces record breaking deliveries"}]
    print(inspector.analyze("TSLA", dummy_news))
