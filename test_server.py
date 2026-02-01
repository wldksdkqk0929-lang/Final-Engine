import json
import os
import sys

# [STEP 1] 모의 데이터(DANGER 상황) 생성
dummy_data = {
    "status": "DANGER",
    "spy_price": 405.20,
    "vix": 36.5,
    "targets": [
        {"ticker": "TSLA", "price": 180.5, "rsi": 25, "sector": "Consumer Discretionary"},
        {"ticker": "NVDA", "price": 420.1, "rsi": 28, "sector": "Technology"}
    ]
}

target_json = "market_status.json"
try:
    with open(target_json, "w", encoding="utf-8") as f:
        json.dump(dummy_data, f, indent=4)
    print(f"\n[TEST] '{target_json}' 생성 완료. (설정값: VIX 36 / DANGER)")
except Exception as e:
    print(f"[ERROR] 데이터 생성 실패: {e}")

# [STEP 2] 서버 가동 명령 안내
print("="*40)
print("🚀 [서버 가동 준비 완료]")
print("잠시 후 서버가 열리면 '브라우저에서 열기' 또는 '포트 8080' 알림을 클릭하십시오.")
print("확인 포인트: 화면에 'RED ALERT' 경고창이 뜨고 배경이 흐려져야 합니다.")
print("="*40 + "\n")

# [STEP 3] 파이썬 내장 서버 실행 (포트 8080)
os.system("python3 -m http.server 8080")
