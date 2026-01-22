# FileSystemimport os
import os
import json
import hashlib
import time
from datetime import datetime

def generate_run_id(mode):
    """Run ID 포맷: YYYYMMDD_HHMM_MODE_HASH"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    short_hash = hashlib.sha256(str(time.time()).encode()).hexdigest()[:4]
    return f"{timestamp}_{mode}_{short_hash}"

def setup_directories(project_root, run_id):
    """history 폴더 생성 및 latest 폴더 준비"""
    base_path = os.path.join(project_root, "data", "history", run_id)
    log_path = os.path.join(base_path, "logs")
    latest_path = os.path.join(project_root, "data", "latest")
    
    os.makedirs(log_path, exist_ok=False) # 이미 존재하면 에러 (불변성 유지)
    os.makedirs(latest_path, exist_ok=True)
    return base_path, latest_path

def save_json(data, filepath):
    """JSON 저장 (실패 시 False 반환)"""
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False

def load_json(filepath):
    """JSON 로드 (없거나 실패 시 None 반환)"""
    if not os.path.exists(filepath): return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if data else None
    except:
        return None
