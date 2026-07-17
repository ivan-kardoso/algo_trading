from __future__ import annotations

from typing import Literal

from ..domain.models.indicator_data import IndicatorData
from ..domain.models.timeframe_slot import TimeframeSlot
from ..domain.ports import IStrategyPort, OHLCVData


class NullStrategy(IStrategyPort):
    def apply_indicators(
        self, datasets: dict[TimeframeSlot, OHLCVData]
    ) -> dict[TimeframeSlot, IndicatorData]:
        return {slot: self._empty_indicators(data) for slot, data in datasets.items()}

    def check_signal(
        self, indicators: dict[TimeframeSlot, IndicatorData]
    ) -> Literal["buy", "sell"] | None:
        return None

    def rhythm_slot(self) -> TimeframeSlot:
        return TimeframeSlot.TIMEFRAME_1

    @staticmethod
    def _empty_indicators(data: OHLCVData) -> IndicatorData:
        return IndicatorData(
            candles=data,
            ema_fast=[None] * len(data),
            ema_medium=[None] * len(data),
            ema_slow=[None] * len(data),
        )
