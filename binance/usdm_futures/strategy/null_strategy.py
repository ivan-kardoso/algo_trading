from __future__ import annotations

from typing import Literal

from ..domain.models.indicator_data import IndicatorData
from ..domain.ports import IStrategyPort, OHLCVData


class NullStrategy(IStrategyPort):
    def apply_indicators(self, data: OHLCVData) -> IndicatorData:
        return IndicatorData(
            candles=data,
            ema_fast=[None] * len(data),
            ema_medium=[None] * len(data),
            ema_slow=[None] * len(data),
        )

    def check_signal(self, data: IndicatorData) -> Literal["buy", "sell"] | None:
        return None
