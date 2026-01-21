import time
class LLMProvider:
    def analyze(self, text): raise NotImplementedError
class GeminiFreeProvider(LLMProvider):
    def analyze(self, text):
        time.sleep(4)
        return {"status": "mock_result"}