from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

from . import OHLCVData

if TYPE_CHECKING:
    from ..models.indicator_data import IndicatorData
    from ..models.timeframe_slot import TimeframeSlot


class IStrategyPort(ABC):
    @abstractmethod
    def apply_indicators(
        self, datasets: dict[TimeframeSlot, OHLCVData]
    ) -> dict[TimeframeSlot, IndicatorData]: ...

    @abstractmethod
    def check_signal(
        self, indicators: dict[TimeframeSlot, IndicatorData]
    ) -> Literal["buy", "sell"] | None: ...

    @abstractmethod
    def rhythm_slot(self) -> TimeframeSlot:
        """Posição de timeframe que dita o ritmo do loop (informada pela estratégia)."""
        ...
