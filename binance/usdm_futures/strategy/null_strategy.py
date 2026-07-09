from __future__ import annotations

from typing import Literal

from ..domain.models.indicator_data import IndicatorData
from ..domain.ports import IStrategyPort, OHLCVData


class NullStrategy(IStrategyPort):
    def apply_indicators(
        self, datasets: dict[str, OHLCVData]
    ) -> dict[str, IndicatorData]:
        return {role: self._empty_indicators(data) for role, data in datasets.items()}

    def check_signal(
        self, indicators: dict[str, IndicatorData]
    ) -> Literal["buy", "sell"] | None:
        return None

    @staticmethod
    def _empty_indicators(data: OHLCVData) -> IndicatorData:
        return IndicatorData(
            candles=data,
            ema_fast=[None] * len(data),
            ema_medium=[None] * len(data),
            ema_slow=[None] * len(data),
        )
