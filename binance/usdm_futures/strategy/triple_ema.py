"""Estratégia Triple EMA — implementação de IStrategyPort.

Multi-timeframe: recebe de 1 a 4 datasets mapeados por papel
(signal/trend/aux_1/aux_2, apenas os preenchidos no TOML).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ..config.strategy_config import StrategySettings
from ..indicators import ema
from ..domain.models.indicator_data import IndicatorData
from ..domain.ports import OHLCVData
from ..domain.ports.strategy import IStrategyPort

if TYPE_CHECKING:
    from loguru import Logger

_FIELD_INDEX: dict[str, int] = {
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
}


class TripleEmaStrategy(IStrategyPort):
    def __init__(
        self,
        settings: StrategySettings,
        timeframes: dict[str, str],
        log: Logger,
    ) -> None:
        self._settings = settings
        self._timeframes = timeframes
        self._log = log
        self._field_index = _FIELD_INDEX[settings.field]
        self._last_alignment: dict[str, Literal["buy", "sell"] | None] = {}

    def apply_indicators(
        self, datasets: dict[str, OHLCVData]
    ) -> dict[str, IndicatorData]:
        result: dict[str, IndicatorData] = {}
        for role, data in datasets.items():
            series = [row[self._field_index] for row in data]
            result[role] = IndicatorData(
                candles=data,
                ema_fast=ema(series, self._settings.fast_period),
                ema_medium=ema(series, self._settings.medium_period),
                ema_slow=ema(series, self._settings.slow_period),
            )
        return result

    def check_signal(
        self, indicators: dict[str, IndicatorData]
    ) -> Literal["buy", "sell"] | None:
        raise NotImplementedError
