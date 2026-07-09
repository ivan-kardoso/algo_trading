"""Estratégia Triple EMA — implementação de IStrategyPort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from loguru import Logger

from ..config.strategy_config import StrategySettings
from ..domain.models.indicator_data import IndicatorData
from ..domain.ports import IStrategyPort, OHLCVData
from ..indicators import ema

_FIELD_INDEX: dict[str, int] = {
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
}


class TripleEmaStrategy(IStrategyPort):
    def __init__(self, settings: StrategySettings, log: Logger) -> None:
        self._settings = settings
        self._field_index = _FIELD_INDEX[settings.field]
        self._log = log
        self._last_alignment: Literal["buy", "sell", "init"] | None = "init"

    def apply_indicators(self, data: OHLCVData) -> IndicatorData:
        series = [row[self._field_index] for row in data]
        return IndicatorData(
            candles=data,
            ema_fast=ema(series, self._settings.fast_period),
            ema_medium=ema(series, self._settings.medium_period),
            ema_slow=ema(series, self._settings.slow_period),
        )

    def check_signal(self, data: IndicatorData) -> Literal["buy", "sell"] | None:

        return None
