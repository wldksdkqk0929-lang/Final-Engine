import json
from datetime import datetime, timedelta

from engine.llm_provider import GeminiProvider
from engine.engines.scoring import calculate_all_scores


class SniperV12Intel:
    def __init__(self, thresholds_config: dict):
        self.config = thresholds_config
        self.daily_cap_max = 50
        self.call_count = 0

        # Real Provider (현재는 PASS Mock)
        self.llm = GeminiProvider()

    def analyze_ticker(self, ticker: str, raw_text: str, current_watch_data: dict = None) -> dict:
        result = {
            "meta": {
                "engine_version": "SNIPER_V12",
                "phase": "PHASE_2_STEP_3",
                "run_mode": "REAL",
                "symbol": ticker,
                "asof_utc": datetime.utcnow().isoformat() + "Z"
            },
            "defense": {
                "fact_check": {"passed": False, "failed_claims": [], "mode": "string_match"},
                "watch_ttl": {"ttl_state": "active"},
                "daily_cap": {"cap_reached": False}
            },
            "scores": {},
            "decision": {"stage": "FAIL", "kill_switch": {"triggered": False, "reasons": []}}
        }

        # ------------------------------------------------------------------
        # Defense 3 — Daily Cap
        # ------------------------------------------------------------------
        if self.call_count >= self.daily_cap_max:
            result["defense"]["daily_cap"]["cap_reached"] = True
            result["decision"]["stage"] = "STOP"
            result["decision"]["kill_switch"] = {
                "triggered": True,
                "reasons": ["DAILY_CAP_REACHED"]
            }
            return result

        self.call_count += 1

        # ------------------------------------------------------------------
        # Defense 2 — TTL
        # ------------------------------------------------------------------
        if current_watch_data:
            created_at = datetime.fromisoformat(
                current_watch_data["created_at"].replace("Z", "")
            )
            expires_at = created_at + timedelta(hours=48)

            result["defense"]["watch_ttl"]["watch_created_utc"] = current_watch_data["created_at"]
            result["defense"]["watch_ttl"]["watch_expires_utc"] = expires_at.isoformat() + "Z"

            if datetime.utcnow() > expires_at:
                result["defense"]["watch_ttl"]["ttl_state"] = "expired"
                result["decision"]["stage"] = "DROP"
                result["decision"]["kill_switch"] = {
                    "triggered": True,
                    "reasons": ["WATCH_TTL_EXPIRED"]
                }
                return result

        # ------------------------------------------------------------------
        # LLM Inference
        # ------------------------------------------------------------------
        try:
            llm_extract = self.llm.analyze(raw_text)
        except Exception as e:
            result["decision"]["stage"] = "FAIL"
            result["decision"]["kill_switch"] = {
                "triggered": True,
                "reasons": ["LLM_CALL_ERROR", str(e)]
            }
            return result

        features = llm_extract.get("features", {})
        claims = llm_extract.get("claims", [])

        # ------------------------------------------------------------------
        # Defense 1 — Fact Check
        # ------------------------------------------------------------------
        fact_check_result = self._run_fact_check(raw_text, claims)
        result["defense"]["fact_check"] = fact_check_result

        # ------------------------------------------------------------------
        # Scoring
        # ------------------------------------------------------------------
        scores = calculate_all_scores(features)
        result["scores"] = scores

        # ------------------------------------------------------------------
        # Final Decision
        # ------------------------------------------------------------------
        stage, reasons = self._apply_thresholds(scores, result["defense"])

        result["decision"]["stage"] = stage
        result["decision"]["kill_switch"]["triggered"] = stage not in ["PASS", "READY", "WATCH"]
        result["decision"]["kill_switch"]["reasons"] = reasons
        result["decision"]["reasons"] = reasons

        return result

    # ==================================================================
    # Internal Logic
    # ==================================================================

    def _run_fact_check(self, raw_text: str, claims: list) -> dict:
        failed = []
        for claim in claims:
            if str(claim.get("value")) not in raw_text:
                failed.append(claim.get("value"))

        return {
            "passed": len(failed) == 0,
            "failed_claims": failed,
            "mode": "string_match"
        }

    def _apply_thresholds(self, scores: dict, defense: dict) -> tuple:
        s = scores

        # ---------------- Kill Switch ----------------
        if not defense["fact_check"]["passed"]:
            return "FAIL", ["FACT_CHECK_FAIL"]

        if defense["daily_cap"]["cap_reached"]:
            return "STOP", ["DAILY_CAP_REACHED"]

        if defense["watch_ttl"].get("ttl_state") == "expired":
            return "DROP", ["WATCH_TTL_EXPIRED"]

        if s["risk_score"] >= 75:
            return "FAIL", ["RISK_TOO_HIGH"]

        if s["liquidity_score"] <= 25:
            return "FAIL", ["LIQUIDITY_TOO_LOW"]

        # ---------------- Stage Logic (PASS 완화) ----------------
        if (
            s["catalyst_score"] >= 50 and
            s["sentiment_score"] >= 60 and
            s["fundamental_score"] >= 60 and
            s["risk_score"] <= 40 and
            s["liquidity_score"] >= 40
        ):
            return "PASS", ["STRONG_MULTI_SIGNAL"]

        if (
            s["catalyst_score"] >= 45 and
            s["sentiment_score"] >= 50 and
            s["risk_score"] <= 50 and
            s["liquidity_score"] >= 35
        ):
            return "READY", ["BUILDING_SIGNAL"]

        if (
            s["catalyst_score"] >= 35 or
            (s["fundamental_score"] >= 55 and s["sentiment_score"] >= 45)
        ):
            return "WATCH", ["WEAK_SIGNAL"]

        return "FAIL", ["INSUFFICIENT_SCORE"]
