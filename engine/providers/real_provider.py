import json
import logging
import os
import re
from typing import Any, Dict, Optional

from google import genai

# -----------------------------
# JSON extraction helpers
# -----------------------------
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_FIRST_JSON_RE = re.compile(r"(\{.*\})", re.DOTALL)

def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    s = text.strip()

    # 1) fenced code block
    m = _JSON_BLOCK_RE.search(s)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass

    # 2) first {...} greedy
    m = _FIRST_JSON_RE.search(s)
    if m:
        candidate = m.group(1).strip()
        # try direct
        try:
            return json.loads(candidate)
        except Exception:
            # last resort: trim trailing junk after last }
            last = candidate.rfind("}")
            if last != -1:
                try:
                    return json.loads(candidate[: last + 1])
                except Exception:
                    return None

    # 3) direct attempt
    try:
        return json.loads(s)
    except Exception:
        return None


class RealProvider:
    """
    Real Gemini Provider (google.genai) + Hunter Doctrine v2 (TUNED)
    - Adds STRUCTURE state: NOT_FORMED / FORMING / FORMED
    - Rebalances score bands to avoid "all WAIT"
    - Forces JSON-only output
    """

    def __init__(self, model_name: str = "models/gemini-pro-latest"):
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is missing!")
        self.model_name = model_name
        self.client = genai.Client(api_key=self.api_key)

        logging.info(f"[RealProvider] Using model: {self.model_name}")

    def analyze(self, symbol: str, payload_dict: Dict[str, Any]) -> Dict[str, Any]:
        raw_text = ""
        try:
            prompt = self._build_prompt(symbol, payload_dict)

            resp = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
            )

            # SDK variants: prefer resp.text, else derive
            raw_text = getattr(resp, "text", None)
            if not raw_text:
                raw_text = str(resp)

            parsed = _extract_json(raw_text)
            if not parsed:
                raise ValueError("JSON_PARSE_ERROR")

            # usage (rough estimation; governance uses these)
            input_tokens = len(prompt) // 4
            output_tokens = len(raw_text) // 4

            return {
                "status": "SUCCESS",
                "strategy_data": parsed,
                "usage": {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
            }

        except Exception as e:
            err = str(e)
            if "JSON_PARSE_ERROR" in err:
                err = "JSON_PARSE_ERROR"

            logging.error(f"❌ Provider Error for {symbol}: {err}")
            if raw_text:
                logging.debug(f"Raw Output (head): {raw_text[:300]}")

            return {
                "status": "FAILED",
                "error": err,
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

    def _build_prompt(self, symbol: str, data: Dict[str, Any]) -> str:
        news = data.get("news_summary", "N/A")
        flow = data.get("flow_summary", "N/A")
        fundamentals = data.get("fundamentals", {}) or {}

        # NOTE: schema must match StrategyOutput exactly.
        return f"""
ROLE: You are SNIPER, an elite TRADER.
You are NOT a company reviewer. You ONLY act when a tradable STRUCTURE exists.
You must focus on DELTA (change), but you are allowed to label "FORMING" when early change starts.

[SNIPER DOCTRINE v2 - TUNED]
- Structure is Necessary. Quality is a Multiplier (only AFTER structure).
- Do NOT auto-BUY good companies.
- However, good companies ARE valid targets WHEN structure is FORMING or FORMED.

[STRUCTURE STATE (choose ONE internally)]
1) NOT_FORMED:
   - No base, no reclaim, no volatility contraction, no change in flow character.
2) FORMING (early setup / pre-trigger):
   - At least ONE early signal exists:
     * downtrend speed slows / lower selling pressure
     * volatility contraction / range tightens
     * volume dries up near lows while price holds (absorption hint)
     * repeated defense of a key level
     * bad news impact weakens (doesn't push price lower)
   - This is NOT an entry yet unless the trigger becomes clear.
3) FORMED (tradable setup):
   - At least TWO confirmations:
     * base after decline + clear support/reclaim
     * volume pattern shifts (accumulation signatures)
     * decisive reclaim of key level / break from compression with volume
     * narrative shift: bad news stops working + buyers appear

[SCORING & DECISION (rebalance)]
- 0-30  : Structure Broken / Downtrend accelerating -> AVOID
- 31-49 : NOT_FORMED / unclear -> WAIT
- 50-69 : FORMING (watch mode) -> WAIT  (BUT: provide what to watch next)
- 70-84 : FORMED -> BUY
- 85-100: FORMED + Quality excellent -> STRONG_BUY
- REDUCE: only if already holding and structure weakens (otherwise use WAIT/AVOID)

[QUALITY (Multiplier rules)]
- Quality NEVER creates a trade alone.
- If Structure=FORMING or FORMED:
  * Strong Quality -> raise confidence and score (may upgrade BUY->STRONG_BUY if FORMED)
  * Normal Quality -> keep within band

[INPUT DATA for {symbol}]
- News Summary:
{news}

- Flow/Price Action:
{flow}

- Fundamentals (context only):
{json.dumps(fundamentals, ensure_ascii=False)}

[OUTPUT REQUIREMENT - JSON ONLY]
Return ONLY a valid JSON object that matches:

{{
  "decision": "STRONG_BUY" | "BUY" | "WAIT" | "REDUCE" | "AVOID",
  "score": (int 0-100),
  "confidence": (float 0.0-1.0),
  "reasoning": "Max 3 lines. Must state: (1) structure state: NOT_FORMED/FORMING/FORMED, (2) what DELTA exists, (3) next trigger to confirm or invalidate.",
  "trading_plan": {{
      "entry_price": "Entry zone or 'WAIT'",
      "stop_loss": "Invalidation level or 'N/A'",
      "target_price": "Target or 'N/A'"
  }}
}}

IMPORTANT:
- If you choose WAIT with score 50-69, you MUST describe a concrete next trigger (what price/flow change would upgrade to BUY).
- Avoid generic phrases like "static snapshot" without specifying what is missing.
""".strip()
