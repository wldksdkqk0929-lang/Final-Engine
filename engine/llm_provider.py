"""
DEPRECATED MODULE

GeminiProvider (KILL-MOCK)는 Phase-4D부터 더 이상 사용하지 않는다.
모든 LLM 접근은 engine.providers.* 경로의 Provider를 통해서만 수행한다.

이 파일은 과거 import 호환성을 위해 남겨둔다.
"""

class GeminiProvider:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "GeminiProvider is deprecated. "
            "Use engine.providers.factory.get_provider() instead."
        )
