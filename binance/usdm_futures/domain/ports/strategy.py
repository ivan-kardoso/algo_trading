from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

from . import OHLCVData

if TYPE_CHECKING:
    from ..models.indicator_data import IndicatorData


class IStrategyPort(ABC):
    @abstractmethod
    def apply_indicators(
        self, datasets: dict[str, OHLCVData]
    ) -> dict[str, IndicatorData]: ...

    @abstractmethod
    def check_signal(
        self, indicators: dict[str, IndicatorData]
    ) -> Literal["buy", "sell"] | None: ...
