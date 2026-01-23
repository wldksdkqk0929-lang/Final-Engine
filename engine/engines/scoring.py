# ==============================================================================
# SNIPER V12 — Deterministic Scoring Engine
# ==============================================================================

def clamp(value, min_v=0, max_v=100):
    try:
        return max(min_v, min(max_v, float(value)))
    except Exception:
        return min_v


def safe_div(n, d, default=0.0):
    try:
        if d == 0:
            return default
        return n / d
    except Exception:
        return default


# ------------------------------------------------------------------------------
# Individual Score Functions
# ------------------------------------------------------------------------------

def calculate_fundamental_score(features: dict) -> int:
    score = 0

    revenue_growth = features.get("revenue_growth_pct", 0)
    eps_revision = features.get("eps_revision_pct", 0)
    margin_trend = features.get("margin_trend", "flat")

    if revenue_growth >= 20:
        score += 40
    elif revenue_growth >= 10:
        score += 30
    elif revenue_growth >= 0:
        score += 15

    if eps_revision >= 15:
        score += 40
    elif eps_revision >= 5:
        score += 25
    elif eps_revision > 0:
        score += 10

    if margin_trend == "expand":
        score += 20
    elif margin_trend == "flat":
        score += 10

    return int(clamp(score))


def calculate_sentiment_score(features: dict) -> int:
    pos = features.get("positive_keywords_count", 0)
    neg = features.get("negative_keywords_count", 0)
    tone = features.get("headline_tone", 0)

    keyword_ratio = safe_div(pos, (pos + neg), 0.5)

    score = 0
    score += clamp(keyword_ratio * 60)
    score += clamp((tone + 1) * 20)

    return int(clamp(score))


def calculate_catalyst_score(features: dict) -> int:
    ctype = features.get("catalyst_type")
    strength = features.get("catalyst_strength", "weak")

    base = {
        "earnings": 40,
        "regulation": 35,
        "product": 30,
        "mna": 45
    }.get(ctype, 10)

    multiplier = {
        "weak": 0.7,
        "medium": 1.0,
        "strong": 1.3
    }.get(strength, 0.7)

    return int(clamp(base * multiplier))


def calculate_risk_score(features: dict) -> int:
    score = 0

    debt = features.get("debt_ratio_pct", 0)
    volatility = features.get("earnings_volatility_pct", 0)

    if debt >= 150:
        score += 40
    elif debt >= 80:
        score += 25
    elif debt >= 40:
        score += 10

    if volatility >= 50:
        score += 30
    elif volatility >= 25:
        score += 15

    if features.get("lawsuit_flag"):
        score += 20

    if features.get("regulatory_risk_flag"):
        score += 20

    return int(clamp(score))


def calculate_liquidity_score(features: dict) -> int:
    volume = features.get("avg_daily_volume_usd", 0)
    market_cap = features.get("market_cap_usd", 0)
    spread = features.get("bid_ask_spread_pct", 1)

    score = 0

    if volume >= 50_000_000:
        score += 40
    elif volume >= 10_000_000:
        score += 25
    elif volume >= 1_000_000:
        score += 10

    if market_cap >= 10_000_000_000:
        score += 30
    elif market_cap >= 1_000_000_000:
        score += 20
    elif market_cap >= 300_000_000:
        score += 10

    if spread <= 0.1:
        score += 30
    elif spread <= 0.3:
        score += 15
    elif spread <= 1.0:
        score += 5

    return int(clamp(score))


# ------------------------------------------------------------------------------
# Unified Interface
# ------------------------------------------------------------------------------

def calculate_all_scores(features: dict) -> dict:
    return {
        "fundamental_score": calculate_fundamental_score(features),
        "sentiment_score": calculate_sentiment_score(features),
        "catalyst_score": calculate_catalyst_score(features),
        "risk_score": calculate_risk_score(features),
        "liquidity_score": calculate_liquidity_score(features)
    }
