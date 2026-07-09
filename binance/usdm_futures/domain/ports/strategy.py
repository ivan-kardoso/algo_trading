from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

from . import OHLCVData

if TYPE_CHECKING:
    from ..models.indicator_data import IndicatorData


class IStrategyPort(ABC):
    @abstractmethod
    def apply_indicators(
        self, trend_data: OHLCVData, signal_data: OHLCVData
    ) -> tuple[IndicatorData, IndicatorData]: ...

    @abstractmethod
    def check_signal(
        self, trend: IndicatorData, signal: IndicatorData
    ) -> Literal["buy", "sell"] | None: ...
