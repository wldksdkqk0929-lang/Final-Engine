# ==========================================
# 3. Re-Ignition Engine V2 (Component Scoring)
# ==========================================

def calculate_structure_quality(base_a, base_b, base_a_date, base_b_date):
    """
    [Component 1] Structure Quality (Max 30)
    - Higher Low 강도 및 기간 안정성 평가
    """
    try:
        score = 0
        
        # 1. Higher Low Ratio (Base B / Base A) -> Max 15
        if base_a == 0: return 0
        ratio = base_b / base_a
        
        if 1.03 <= ratio <= 1.15: # 3% ~ 15% 사이의 이상적인 Higher Low
            score += 15
        elif 1.00 < ratio < 1.03: # 너무 얕은 반등
            score += 5
        elif ratio > 1.15: # 너무 급격한 V자 반등 (불안정)
            score += 7
        else: # 저점 갱신 (Invalid)
            return 0 

        # 2. Time Duration (Base B Date - Base A Date) -> Max 15
        # 바닥을 다지는 기간이 충분해야 함
        da = datetime.strptime(base_a_date, "%Y-%m-%d")
        db = datetime.strptime(base_b_date, "%Y-%m-%d")
        days = (db - da).days
        
        if days >= 30: score += 15       # 1달 이상 바닥 다짐 (최상)
        elif days >= 14: score += 10     # 2주 이상 (양호)
        elif days >= 7: score += 5       # 1주 (최소)
        else: score += 0                 # 너무 급함
        
        return min(30, score)
    except: return 0

def calculate_compression_energy(hist):
    """
    [Component 2] Compression Energy (Max 25)
    - 변동성(ATR) 및 거래량 축소 확인 (응축)
    """
    try:
        score = 0
        if len(hist) < 60: return 10 # 데이터 부족 시 기본점수
        
        # 최근 10일 vs 과거 60일 데이터 비교
        recent_window = 10
        past_window = 60
        
        # 1. Volatility Compression (ATR) -> Max 15
        # 최근 변동폭이 과거 평균보다 줄어들어야 함 (에너지 응축)
        high_low = hist["High"] - hist["Low"]
        atr_recent = high_low.tail(recent_window).mean()
        atr_past = high_low.tail(past_window).mean()
        
        if atr_past == 0: return 0
        atr_ratio = atr_recent / atr_past
        
        if atr_ratio < 0.7: score += 15      # 30% 이상 변동성 축소 (강력 응축)
        elif atr_ratio < 0.9: score += 10    # 10% 이상 축소
        elif atr_ratio < 1.1: score += 5     # 평이함
        
        # 2. Volume Contraction -> Max 10
        # 거래량이 말라야 매도세 소진
        vol_recent = hist["Volume"].tail(recent_window).mean()
        vol_past = hist["Volume"].tail(past_window).mean()
        
        if vol_past == 0: return 0
        vol_ratio = vol_recent / vol_past
        
        if vol_ratio < 0.7: score += 10      # 거래량 급감 (매물 소화 완료)
        elif vol_ratio < 0.9: score += 5
        
        return min(25, score)
    except: return 0

def calculate_breakout_proximity(current_price, pivot_price, hist):
    """
    [Component 3] Breakout Proximity (Max 25)
    - Pivot 접근도 및 모멘텀
    """
    try:
        score = 0
        if pivot_price == 0: return 0
        
        # 1. Distance to Pivot -> Max 15
        dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        if current_price > pivot_price: # 이미 돌파
            score += 25 # 만점 (Breakout)
        elif 0 <= dist_pct <= 3.0: # 초근접 (Ready)
            score += 15
        elif 3.0 < dist_pct <= 8.0: # 가시권 (Watch)
            score += 10
        elif dist_pct <= 15.0:
            score += 5
            
        # 2. Momentum (MA Trend) -> Max 10
        # 5일선이 20일선 위에 있는가? (단기 정배열)
        ma5 = hist["Close"].rolling(5).mean().iloc[-1]
        ma20 = hist["Close"].rolling(20).mean().iloc[-1]
        
        if ma5 > ma20: score += 10
        
        return min(25, score)
    except: return 0

def calculate_risk_stability(current_price, hist, noise_score=0):
    """
    [Component 4] Risk Stability (Max 20)
    - 가격 안정성 및 노이즈 패널티
    """
    try:
        score = 20 # 기본 20점에서 감점 방식
        
        # 1. Volatility Risk (ATR Ratio)
        # 가격 대비 변동성이 너무 크면 감점
        high_low = hist["High"] - hist["Low"]
        atr = high_low.tail(20).mean()
        vol_ratio = atr / current_price if current_price > 0 else 0
        
        if vol_ratio > 0.05: score -= 5      # 변동성 5% 초과 (위험)
        if vol_ratio > 0.08: score -= 5      # 변동성 8% 초과 (매우 위험)
        
        # 2. Noise Penalty
        # 외부 노이즈(뉴스 등)가 있으면 감점
        score -= (noise_score * 5)
        
        return max(0, score)
    except: return 0

def analyze_reignition_structure(hist, noise_score=0):
    """
    [RIB V2 Engine] 4-Component Scoring System
    Total Score = Struct(30) + Compression(25) + Proximity(25) + Risk(20) = 100
    """
    try:
        if len(hist) < 120: return None
        
        recent = hist.tail(120).copy()
        current_price = recent["Close"].iloc[-1]
        
        # --- Base Identification Logic (기존 유지) ---
        base_a_idx = recent["Close"].idxmin()
        base_a_price = recent.loc[base_a_idx]["Close"]
        base_a_date = base_a_idx.strftime("%Y-%m-%d")
        
        post_base_a = recent.loc[base_a_idx:]
        if len(post_base_a) < 5: 
            return {"status": "FORMING_A", "rib_score": 0, "grade": "IGNORE", "priority": 4}

        pivot_idx = post_base_a["Close"].idxmax()
        pivot_price = post_base_a.loc[pivot_idx]["Close"]
        pivot_date = pivot_idx.strftime("%Y-%m-%d")
        
        if pivot_date == base_a_date:
             return {"status": "BOUNCING", "rib_score": 10, "grade": "IGNORE", "priority": 4}

        post_pivot = post_base_a.loc[pivot_idx:]
        if len(post_pivot) < 3: 
             return {"status": "AT_PIVOT", "rib_score": 20, "grade": "IGNORE", "priority": 4}

        base_b_idx = post_pivot["Close"].idxmin()
        base_b_price = post_pivot.loc[base_b_idx]["Close"]
        base_b_date = base_b_idx.strftime("%Y-%m-%d")

        # Invalid Logic (Kill Switch)
        if base_b_price < base_a_price: # 저점 갱신
            return {"status": "INVALID (Low Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}
        if current_price < base_b_price: # 2차 저점 붕괴
            return {"status": "INVALID (B Broken)", "rib_score": 0, "grade": "IGNORE", "priority": 99}

        # --- [V2] Component Scoring ---
        
        # 1. Structure Quality (30)
        s_struct = calculate_structure_quality(base_a_price, base_b_price, base_a_date, base_b_date)
        
        # 2. Compression Energy (25)
        s_comp = calculate_compression_energy(hist)
        
        # 3. Breakout Proximity (25)
        s_prox = calculate_breakout_proximity(current_price, pivot_price, hist)
        
        # 4. Risk Stability (20)
        s_risk = calculate_risk_stability(current_price, hist, noise_score)
        
        # Total Score
        total_score = s_struct + s_comp + s_prox + s_risk
        
        # --- Grading & Priority ---
        if pivot_price == 0: dist_pct = 0
        else: dist_pct = (pivot_price - current_price) / pivot_price * 100
        
        status = ""
        grade = "IGNORE"
        priority = 4
        trigger_msg = ""
        badge_color = "#95a5a6"

        if current_price > pivot_price:
            status = "🔥 RIB BREAKOUT"
            grade = "ACTION"
            priority = 1
            trigger_msg = "Pivot 돌파 확인. 모멘텀 발생."
            badge_color = "#e74c3c"
        elif dist_pct <= 3.0:
            status = "🚀 RIB READY"
            grade = "SETUP"
            priority = 2
            trigger_msg = f"돌파 임박 ({dist_pct:.1f}%). 응축도 확인."
            badge_color = "#e67e22"
        elif dist_pct <= 10.0: # 범위 소폭 확대 (정밀 점수제가 도입되었으므로)
            status = "👀 RIB WATCH"
            grade = "RADAR"
            priority = 3
            trigger_msg = f"구조 형성 중 ({dist_pct:.1f}%)."
            badge_color = "#f1c40f"
        else:
            status = "💤 RIB EARLY"
            grade = "IGNORE"
            priority = 4
            trigger_msg = "이격도 큼."

        return {
            "base_a": base_a_price, "base_a_date": base_a_date,
            "pivot": pivot_price, "pivot_date": pivot_date,
            "base_b": base_b_price, "base_b_date": base_b_date,
            "distance": dist_pct,
            "status": status,
            "grade": grade,
            "priority": priority,
            "trigger_msg": trigger_msg,
            "badge_color": badge_color,
            "rib_score": int(total_score), # 정수화
            "components": { # 상세 점수 리포트
                "struct": s_struct,
                "comp": s_comp,
                "prox": s_prox,
                "risk": s_risk
            }
        }

    except Exception as e:
        return None
