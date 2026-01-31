import json
import os
import sys
from datetime import datetime

# 모듈 경로 추가 (현재 위치 기준)
sys.path.append(os.getcwd())

from engine.v9_hunter.collector import NewsCollector
from engine.v9_hunter.inspector import NewsInspector

class HunterEngine:
    def __init__(self):
        self.collector = NewsCollector()
        self.inspector = NewsInspector()
        self.output_file = "Target_Dossier.json"

    def run_mission(self):
        print("🚀 [Hunter] Mission Start: Seeking Targets...")

        # 1. [RADAR] Phase-6N 레이더 가동 (테스트용 고정 타겟)
        # *실전에서는 여기서 run_phase6n 로직을 호출해 진짜 타겟을 받아옵니다.
        # *지금은 파이프라인 연결 테스트를 위해 3대장을 강제 지정합니다.
        candidates = [
            {"symbol": "TSLA", "tech_score": 92.5},
            {"symbol": "NVDA", "tech_score": 88.0},
            {"symbol": "PLTR", "tech_score": 45.0} # 탈락 테스트용
        ]
        
        dossier_list = []

        # 2. [LOOP] 각 후보에 대해 눈(Collector)과 뇌(Inspector) 가동
        for cand in candidates:
            symbol = cand["symbol"]
            tech_score = cand["tech_score"]
            
            # A. 뉴스 수집 (Eyes)
            news = self.collector.get_news(symbol)
            
            # B. 정밀 심문 (Brain)
            analysis = self.inspector.analyze(symbol, news)
            
            # C. 결과 합치기 (Synthesis)
            # 기술 점수와 명분 점수를 합산하여 최종 등급 판정
            final_entry = {
                "symbol": symbol,
                "tech_score": tech_score,
                "reasoning_score": analysis["reasoning_score"],
                "risk_level": analysis["risk_level"],
                "action": analysis["action"], # ENGAGE / WATCH / DISCARD
                "thesis": {
                    "summary": analysis["thesis_summary"],
                    "news_count": len(news)
                }
            }
            dossier_list.append(final_entry)
            print(f"   👉 Processed {symbol}: Action={analysis['action']}")

        # 3. [LOCK] 결과 파일 저장 (Target_Dossier.json)
        final_dossier = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "version": "V9.0",
            "dossier": dossier_list
        }

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(final_dossier, f, indent=2)
            
        print(f"\n✅ [Hunter] Mission Complete. Dossier saved to {self.output_file}")

if __name__ == "__main__":
    hunter = HunterEngine()
    hunter.run_mission()
