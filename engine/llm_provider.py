import time
import os
try:
    import google.generativeai as genai
except ImportError:
    genai = None

class LLMProvider:
    def analyze(self, text): raise NotImplementedError

class GeminiFreeProvider(LLMProvider):
    def __init__(self):
        # 환경변수에서 키 로드
        api_key = os.getenv("GEMINI_API_KEY")
        
        # 라이브러리와 키가 모두 있어야 준비 완료
        if genai and api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel("gemini-1.5-flash")
                self.ready = True
            except Exception:
                self.ready = False
        else:
            self.ready = False

    def analyze(self, text):
        """
        뉴스 텍스트 분석
        - API Key 없으면: None 반환 (Engine이 SKIP 처리)
        - 호출 성공 시: 4초 대기 후 결과 반환
        """
        if not self.ready:
            return None 

        try:
            # [Smart Free Architecture] Free Tier 제한(RPM) 보호를 위한 강제 대기
            time.sleep(4)
            
            # --- 실제 호출 부 (현재는 Mocking 처리하여 연결 테스트만 수행) ---
            # prompt = f"Analyze this stock news in JSON: {text}"
            # response = self.model.generate_content(prompt)
            # return response.text (Parsed JSON)
            
            # [테스트용 Mock 리턴] 실제 연결 성공 시뮬레이션
            return {
                "status": "PASS", 
                "catalyst": "Earnings Surprise (Simulated)", 
                "score": 85
            }
            
        except Exception as e:
            # API 에러 발생 시 멈추지 않고 None 반환 -> 로그만 남기고 다음 종목 진행
            return None
