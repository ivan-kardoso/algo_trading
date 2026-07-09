from __future__ import annotations

from typing import Literal

from ..domain.models.indicator_data import IndicatorData
from ..domain.ports import IStrategyPort, OHLCVData


class NullStrategy(IStrategyPort):
    def apply_indicators(
        self, trend_data: OHLCVData, signal_data: OHLCVData
    ) -> tuple[IndicatorData, IndicatorData]:
        return (self._empty_indicators(trend_data), self._empty_indicators(signal_data))

    def check_signal(
        self, trend: IndicatorData, signal: IndicatorData
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
