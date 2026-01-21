# Resume Logicfrom engine.utils.filesystem import load_json

def check_resume_condition(filepath, required_keys=[]):
    """
    Resume 조건: 
    1. 파일 존재 
    2. JSON 로딩 성공 
    3. (옵션) 필수 키 포함 여부
    """
    data = load_json(filepath)
    if data is None: return False
    
    if required_keys:
        for k in required_keys:
            # 리스트 형태인 경우 첫 번째 항목 검사
            if isinstance(data, list):
                if len(data) > 0 and isinstance(data[0], dict) and k not in data[0]:
                    return False
                if len(data) == 0: # 빈 리스트는 유효하지 않다고 판단
                    return False
            # 딕셔너리 형태인 경우 키 검사
            elif isinstance(data, dict):
                if k not in data:
                    return False
    return True
