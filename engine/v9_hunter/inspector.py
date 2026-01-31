
import os
import json
import requests
from datetime import datetime

class NewsInspector:
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY")
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model_endpoint = None

    def get_working_model(self):
        try:
            url = f"{self.base_url}/models?key={self.api_key}"
            response = requests.get(url)
            if response.status_code != 200: return None
            
            models = response.json().get("models", [])
            candidates = [m for m in models if "generateContent" in m.get("supportedGenerationMethods", [])]
            
            # 우선순위: Flash -> Pro -> 아무거나
            for m in candidates:
                if "gemini-1.5-flash" in m["name"]: return m["name"]
            for m in candidates:
                if "gemini-pro" in m["name"]: return m["name"]
            if candidates: return candidates[0]["name"]
            return None
        except:
            return None

    def analyze(self, symbol, news_list):
        if not news_list:
            return {"symbol": symbol, "action": "DISCARD", "thesis": {"summary": "No news."}}

        if not self.model_endpoint:
            model_name = self.get_working_model()
            if model_name:
                print(f"   🤖 Found Model: {model_name}")
                self.model_endpoint = f"{self.base_url}/{model_name}:generateContent"
            else:
                return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": "No AI Model Found"}}

        news_text = "\n".join([f"- {n["title"]}" for n in news_list[:3]])
        
        # JSON 요청 생성
        payload = {
            "contents": [{
                "parts": [{
                    "text": f"Analyze {symbol} news:\n{news_text}\nOutput JSON: {{ action: WATCH/DISCARD, score: 0-100, risk: LOW/MED, summary: One sentence in Korean }}"
                }]
            }]
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
            
            return {
                "symbol": symbol,
                "action": data.get("action", "WATCH"),
                "reasoning_score": data.get("score", 50),
                "risk_level": data.get("risk", "MEDIUM"),
                "thesis": {"summary": data.get("summary", "Analysis Done")},
                "last_updated": datetime.now().strftime("%H:%M")
            }
        except:
            return {"symbol": symbol, "action": "WATCH", "risk_level": "ERROR", "thesis": {"summary": f"News: {news_list[0]["title"]}"}}
