import os
import sys
import shutil
import yaml
from datetime import datetime

# 경로 설정 (실행 위치 기준)
sys.path.append(os.getcwd())

from engine.utils.logger import SystemLogger
from engine.utils.filesystem import generate_run_id, setup_directories, save_json, load_json
from engine.utils.resume import check_resume_condition
from engine.llm_provider import GeminiFreeProvider

def load_config():
    """config/base.yaml 로드 (없으면 기본값)"""
    config_path = os.path.join("config", "base.yaml")
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except: pass
    return {"mode": "BALANCED"}

class SniperOrchestrator:
    def __init__(self):
        # 1. 설정 로드 및 Run ID 생성
        self.config = load_config()
        self.mode = self.config.get("mode", "BALANCED")
        self.run_id = generate_run_id(self.mode)
        self.project_root = os.getcwd()
        
        # 2. 디렉토리 구축 (history/RUN_ID)
        self.path, self.latest_path = setup_directories(self.project_root, self.run_id)
        
        # 3. 로거 가동
        self.logger = SystemLogger(self.path)
        self.logger.log(f"🔥 SNIPER V12 Orchestrator Initialized. Run ID: {self.run_id}")
        self.exit_code = 0

        # 4. Run Meta 저장
        save_json({
            "run_id": self.run_id,
            "config": self.config,
            "start_time": datetime.now().isoformat()
        }, os.path.join(self.path, "run_meta.json"))

    def run(self):
        try:
            # --- Stage 1: Universe Generation (Stub) ---
            self.logger.log("🚀 [Stage 1] Universe Generation...")
            universe_path = os.path.join(self.path, "1_universe.json")
            
            if not check_resume_condition(universe_path):
                # 테스트용 유니버스 생성 (실제 구현 시 API 호출로 대체)
                mock_universe = [
                    {"symbol": "AAPL", "name": "Apple"}, 
                    {"symbol": "TSLA", "name": "Tesla"}, 
                    {"symbol": "NVDA", "name": "Nvidia"}
                ]
                save_json(mock_universe, universe_path)
                self.logger.log(f"   -> Universe Created: {len(mock_universe)} targets")
            else:
                self.logger.log("   -> Skipped (Resume)")

            # --- Stage 2: News Intelligence (LLM) ---
            self.logger.log("🧠 [Stage 2] News Intelligence (Gemini Free)...")
            intel_path = os.path.join(self.path, "2_intel.json")
            
            if not check_resume_condition(intel_path):
                llm = GeminiFreeProvider()
                
                if not llm.ready:
                    self.logger.log("   ⚠️ LLM Not Ready (Check API Key). Skipping analysis.", "WARNING")
                    # 키가 없어도 멈추지 않고 빈 결과로 진행
                    save_json([], intel_path)
                else:
                    results = []
                    universe = load_json(universe_path) or []
                    
                    for i, stock in enumerate(universe):
                        sym = stock['symbol']
                        self.logger.log(f"   [{i+1}/{len(universe)}] Analyzing {sym}...")
                        
                        # 뉴스 분석 요청 (Mock Text)
                        res = llm.analyze(f"Recent news about {sym}")
                        
                        if res:
                            stock.update(res)
                            results.append(stock)
                            self.logger.log(f"     -> {sym}: {res.get('status')} (Simulated)")
                        else:
                            self.logger.log(f"     -> {sym}: FAIL/SKIP")
                    
                    save_json(results, intel_path)
            else:
                self.logger.log("   -> Skipped (Resume)")

            # --- Stage 3: Finalize ---
            self.finalize()

        except Exception as e:
            self.logger.log(f"❌ CRITICAL FAILURE: {e}", "ERROR")
            sys.exit(99)

    def finalize(self):
        self.logger.log("🏁 Finalizing Run...")
        # Latest 폴더로 결과물 동기화 (덮어쓰기)
        for f in os.listdir(self.path):
            src = os.path.join(self.path, f)
            dst = os.path.join(self.latest_path, f)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
        
        self.logger.log("✅ Sync to 'data/latest' complete.")
        self.logger.log("✅ SNIPER V12 Mission Complete.")
