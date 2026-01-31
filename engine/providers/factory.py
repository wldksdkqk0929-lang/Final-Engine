import os

from engine.providers.mock_provider import MockProvider
from engine.providers.real_provider import RealProvider


def get_provider():
    """
    Provider Factory
    - MOCK (default)
    - REAL  (SNIPER_PROVIDER_MODE=REAL)
    """

    mode = os.getenv("SNIPER_PROVIDER_MODE", "MOCK").upper()

    if mode == "REAL":
        print("🚨 [Provider] REAL mode selected. (cost/risk enabled)")
        return RealProvider()

    print("✅ [Provider] MOCK mode selected. (safe)")
    return MockProvider()
