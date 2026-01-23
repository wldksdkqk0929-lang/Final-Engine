"""
Gemini Provider (Phase-2 KILL Forced Mock Version)
위험도를 의도적으로 폭발시켜 Kill-Switch 검증
"""

class GeminiProvider:
    def __init__(self):
        print("💣 [GeminiProvider] KILL-MOCK provider initialized.")

    def analyze(self, text: str) -> dict:
        """
        Kill-Switch 강제 검증용 Mock Output
        Risk Score가 임계값을 초과하도록 설계됨
        """

        return {
            "claims": [
                {"value": "lawsuit", "type": "keyword"},
                {"value": "regulatory", "type": "keyword"},
            ],
            "features": {
                # Fundamental (양호)
                "revenue_growth_pct": 15,
                "eps_revision_pct": 8,
                "margin_trend": "flat",

                # Sentiment (보통)
                "positive_keywords_count": 5,
                "negative_keywords_count": 4,
                "headline_tone": 0.1,

                # Catalyst (약함)
                "catalyst_type": "product",
                "catalyst_strength": "weak",

                # 💥 Risk 폭발
                "debt_ratio_pct": 180,              # +40
                "earnings_volatility_pct": 65,      # +30
                "lawsuit_flag": True,               # +20
                "regulatory_risk_flag": True,       # +20
                # → Risk Score = 110 (Clamp → 100)

                # Liquidity (정상)
                "avg_daily_volume_usd": 80_000_000,
                "market_cap_usd": 12_000_000_000,
                "bid_ask_spread_pct": 0.08,
            }
        }
