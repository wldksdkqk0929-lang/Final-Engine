from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, Dict


# ==========================
# Input Payload Contract
# ==========================

class MarketPayload(BaseModel):
    symbol: str

    news_summary: str = Field(..., min_length=20, max_length=2000)
    flow_summary: str = Field(..., min_length=20, max_length=1200)
    fundamentals: Dict[str, str]

    @validator("symbol")
    def normalize_symbol(cls, v):
        return v.upper().strip()


class AnalysisRequest(BaseModel):
    request_id: str
    payload: MarketPayload


# ==========================
# Output Contract
# ==========================

class StrategyOutput(BaseModel):
    decision: str
    score: int
    confidence: float
    reasoning: str
    trading_plan: Dict[str, str]

    # --- Quant Injected Fields ---
    structure_state: str
    price_signal: bool
    flow_signal: bool
    watchlist: bool
    support_distance_pct: float


class AnalysisResult(BaseModel):
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.now)

    strategy: Optional[StrategyOutput] = None
    raw_response: Optional[str] = None

    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
