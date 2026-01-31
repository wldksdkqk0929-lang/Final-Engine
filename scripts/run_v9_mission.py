import sys
import os
import pandas as pd
import json
from datetime import datetime

# 경로 설정
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine.v9_hunter.collector import NewsCollector
from engine.v9_hunter.inspector import NewsInspector

def load_universe():
    """CSV 파일에서 타겟 리스트 로드"""
    if os.path.exists('universe.csv'):
        try:
            df = pd.read_csv('universe.csv')
            return df['symbol'].tolist()
        except:
            return ['TSLA', 'NVDA', 'PLTR'] # 실패시 기본값
    return ['TSLA', 'NVDA', 'PLTR']

def run_mission():
    print(f"🚀 [Hunter] Mission Start: Loading Targets...")
    
    # 1. 타겟 로드 (최대 50개로 제한 - API 보호)
    # 사령관님, 무료 키 보호를 위해 한 번에 500개를 다 돌리면 차단당할 수 있어
    # 우선 상위 20개만 시범적으로 돌리도록 설정했습니다. 
    # (원하시면 [:20]을 지우면 전체가 돌아갑니다)
    targets = load_universe()[:20] 
    
    print(f"🎯 Targets Identified: {len(targets)} sectors")

    collector = NewsCollector()
    inspector = NewsInspector()
    
    dossier = []
    
    for symbol in targets:
        print(f"📡 Scanning: {symbol}...")
        try:
            news = collector.fetch_news(symbol)
            if not news:
                continue
                
            intel = inspector.analyze(symbol, news)
            
            # 유의미한 결과(WATCH 이상)만 기록하거나, 
            # 아니면 다 기록하되 대시보드에서 필터링
            dossier.append(intel)
            
            print(f"   👉 Result: {intel.get('action', 'UNKNOWN')}")
        except Exception as e:
            print(f"   ❌ Error on {symbol}: {e}")

    # 리포트 저장
    report = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "version": "V9.0",
        "dossier": dossier
    }
    
    with open("Target_Dossier.json", "w", encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✅ [Hunter] Mission Complete. {len(dossier)} reports filed.")

if __name__ == "__main__":
    run_mission()
