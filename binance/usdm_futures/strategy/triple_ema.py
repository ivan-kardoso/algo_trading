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
    PRIMARY_TREND = TimeframeSlot.TIMEFRAME_1
    SECONDARY_TREND = TimeframeSlot.TIMEFRAME_2
    SIGNAL = TimeframeSlot.TIMEFRAME_3
    AUXILIARY = TimeframeSlot.TIMEFRAME_4


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
        self._primary_trend_lock_pending: bool = True
        self._primary_trend_blocked: Literal["buy", "sell"] | None = None
        self._primary_trend_released: bool = False
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

    def _check_alignment(
        self, f: float, m: float, s: float
    ) -> Literal["buy", "sell"] | None:
        return "buy" if f > m > s else "sell" if f < m < s else None

    # chamado por SymbolRunner
    def rhythm_slot(self) -> TimeframeSlot:
        return Role.SIGNAL.value

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
            self._log.log(
                "ALIGN", f"Timeframe {timeframe} - Triple EMA alinhada para compra."
            )
        elif alignment == "sell":
            self._log.log(
                "ALIGN", f"Timeframe {timeframe} - Triple EMA alinhada para venda."
            )
        else:
            self._log.log("ALIGN", f"Timeframe {timeframe} - Triple EMA sem alinhamento.")

        return alignment

    def _is_primary_trend_released(
        self, trend_side: Literal["buy", "sell"] | None
    ) -> bool:
        if self._primary_trend_released:
            return True

        if self._primary_trend_lock_pending:
            self._primary_trend_blocked = trend_side
            self._primary_trend_lock_pending = False
            if trend_side is not None:
                self._log.log(
                    "LOCK",
                    f"Alinhamento inicial {'compra.' if self._primary_trend_blocked == 'buy' else 'venda.' if self._primary_trend_blocked == 'sell' else 'indefinido.'} Aguardando reversão.",
                )

        if trend_side != self._primary_trend_blocked:
            self._primary_trend_released = True
            self._log.log("UNLOCK", "Trava liberada - operação habilitada.")
            return True

        return False

    def check_signal(
        self, indicators: dict[TimeframeSlot, IndicatorData]
    ) -> Literal["buy", "sell"] | None:
        primary_trend_side = self._is_aligned(indicators, Role.PRIMARY_TREND)
        if primary_trend_side is None:
            return None

        if not self._is_primary_trend_released(primary_trend_side):
            return None

        secondary_trend_side = self._is_aligned(indicators, Role.SECONDARY_TREND)
        signal_side = self._is_aligned(indicators, Role.SIGNAL)

        if secondary_trend_side and signal_side != primary_trend_side:
            self._armed = None
            return None

        return None
