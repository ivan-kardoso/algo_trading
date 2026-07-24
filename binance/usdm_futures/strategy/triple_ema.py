"""Estratégia Triple EMA — implementação de IStrategyPort.

Multi-timeframe: recebe de 1 a 4 datasets mapeados por posição de timeframe
(`TimeframeSlot`). O mapeamento papel -> posição é definido pelo enum `Role`,
interno à estratégia.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from enum import Enum

from ..config.strategy_config import StrategySettings
from ..indicators import ema
from ..domain.models.indicator_data import IndicatorData
from ..domain.models.timeframe_slot import TimeframeSlot
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


class Role(Enum):
    TREND_1 = TimeframeSlot.TIMEFRAME_1
    TREND_2 = TimeframeSlot.TIMEFRAME_2
    SIGNAL = TimeframeSlot.TIMEFRAME_3
    AUX_1 = TimeframeSlot.TIMEFRAME_4


class TripleEmaStrategy(IStrategyPort):
    def __init__(
        self,
        settings: StrategySettings,
        timeframes: dict[TimeframeSlot, str],
        log: Logger,
    ) -> None:
        self._settings = settings
        self._timeframes = timeframes
        self._log = log
        self._field_index = _FIELD_INDEX[settings.emas.field]
        self._trend_lock_pending: bool = True
        self._trend_blocked: Literal["buy", "sell"] | None = None
        self._trend_released: bool = False
        self._armed: Literal["buy", "sell"] | None = None

    def apply_indicators(
        self, datasets: dict[TimeframeSlot, OHLCVData]
    ) -> dict[TimeframeSlot, IndicatorData]:
        result: dict[TimeframeSlot, IndicatorData] = {}
        for slot, data in datasets.items():
            series = [row[self._field_index] for row in data]
            result[slot] = IndicatorData(
                candles=data,
                ema_fast=ema(series, self._settings.emas.fast_period),
                ema_medium=ema(series, self._settings.emas.medium_period),
                ema_slow=ema(series, self._settings.emas.slow_period),
            )
        return result

    def _check_alignment(self, f: float, m: float, s: float) -> Literal["buy", "sell"] | None:
        return "buy" if f > m > s else "sell" if f < m < s else None

    def _is_aligned(
        self, indicators: dict[TimeframeSlot, IndicatorData], role: Role
    ) -> Literal["buy", "sell"] | None:
        slot = role.value
        data = indicators.get(slot)
        if data is None:
            return None

        i = len(data.candles) - 1
        if i < 0:
            return None

        f = data.ema_fast[i]
        m = data.ema_medium[i]
        s = data.ema_slow[i]

        if f is None or m is None or s is None:
            return None

        timeframe = self._timeframes.get(slot, slot)
        alignment = self._check_alignment(f, m, s)

        if alignment == "buy":
            self._log.log("ALIGN", f"Timeframe {timeframe} - Triple EMA alinhada para compra.")
        elif alignment == "sell":
            self._log.log("ALIGN", f"Timeframe {timeframe} - Triple EMA alinhada para venda.")
        else:
            self._log.log("ALIGN", f"Timeframe {timeframe} - Triple EMA sem alinhamento.")

        return alignment

    def check_signal(
        self, indicators: dict[TimeframeSlot, IndicatorData]
    ) -> Literal["buy", "sell"] | None:
        self._is_aligned(indicators, Role.TREND_1)
        self._is_aligned(indicators, Role.TREND_2)
        self._is_aligned(indicators, Role.SIGNAL)
        return None

    def rhythm_slot(self) -> TimeframeSlot:
        return Role.SIGNAL.value
