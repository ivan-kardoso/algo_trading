from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

from . import OHLCVData

if TYPE_CHECKING:
    from ..models.indicator_data import IndicatorData
    from ..models.role import Role


class IStrategyPort(ABC):
    @abstractmethod
    def apply_indicators(
        self, datasets: dict[Role, OHLCVData]
    ) -> dict[Role, IndicatorData]: ...

    @abstractmethod
    def check_signal(
        self, indicators: dict[Role, IndicatorData]
    ) -> Literal["buy", "sell"] | None: ...
