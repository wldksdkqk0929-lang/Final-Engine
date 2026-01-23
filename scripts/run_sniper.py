# [Imports 추가]
from engine.gatekeeper import LLMGatekeeper
from engine.cache import SniperCacheLayer

# [Init 섹션 추가]
gatekeeper = LLMGatekeeper()
cache_layer = SniperCacheLayer(ttl_minutes=60) # Phase-2E Default

# [Execution Loop 내부 수정]
# 기존: result = engine.analyze_ticker(...) 
# 변경:

# 1. Gatekeeper Check (Auditing)
access_status = gatekeeper.check_access(ticker, request_id=f"REQ_{ticker}_{int(time.time())}")

# 2. Cache Layer Orchestration
try:
    # Lambda로 실제 엔진 실행 함수를 감싸서 전달 (Lazy Execution)
    result = cache_layer.resolve_request(
        provider="gemini",       # 나중에 Config 연동
        model="pro", 
        symbol=ticker, 
        prompt=mock_raw_text,    # Cache Key용 Prompt
        gatekeeper_status=access_status,
        llm_call_func=lambda: engine.analyze_ticker(ticker, mock_raw_text, current_watch_data)
    )
    
    # [결과 처리]
    save_result(ticker, result)
    print(f"   [RESULT] {result['decision']['stage']}")

except PermissionError as e:
    print(f"   ⛔ {e}")
    # Kill-Switch Logic에 따라 루프 중단 or Skip
    if "DAILY_CAP" in str(e): break
    continue