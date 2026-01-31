from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseAnalysisProvider(ABC):
    """
    MOCK/REAL 모두 동일 규격을 강제한다.
    """

    @abstractmethod
    def health_check(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def analyze_symbol(self, symbol: str, data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_usage_stats(self) -> Dict[str, Any]:
        raise NotImplementedError
