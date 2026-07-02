from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from . import OHLCVData
from ..models.indicator_data import IndicatorData


class IStrategyPort(ABC):
    @abstractmethod
    def apply_indicators(self, data: OHLCVData) -> IndicatorData: ...

    @abstractmethod
    def check_signal(self, data: IndicatorData) -> Literal["buy", "sell"] | None: ...
