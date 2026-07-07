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

        # Estado do gatilho (memória entre candles).
        self._armed: Literal["buy", "sell"] | None = None
        # Timestamp do último candle já processado (garante avanço na série).
        self._last_ts: float | None = None

    def apply_indicators(self, data: OHLCVData) -> IndicatorData:
        series = [row[self._field_index] for row in data]
        return IndicatorData(
            candles=data,
            ema_fast=ema(series, self._settings.fast_period),
            ema_medium=ema(series, self._settings.medium_period),
            ema_slow=ema(series, self._settings.slow_period),
        )

    def _check_alignment(
        self, f: float, m: float, s: float
    ) -> Literal["buy", "sell"] | None:
        if f > m > s:
            alignment = "buy"
        elif f < m < s:
            alignment = "sell"
        else:
            alignment = None

        if alignment != self._last_alignment:
            if alignment == "buy":
                self._log.info("Triple EMA alinhada para compra")
            elif alignment == "sell":
                self._log.info("Triple EMA alinhada para venda")
            else:
                self._log.info("Triple EMA sem alinhamento")
            self._last_alignment = alignment

        return alignment

    def check_signal(self, data: IndicatorData) -> Literal["buy", "sell"] | None:
        candles = data.candles
        if not candles:
            return None

        i = len(candles) - 1
        f = data.ema_fast[i]
        m = data.ema_medium[i]
        s = data.ema_slow[i]
        if f is None or m is None or s is None:
            return None

        self._check_alignment(f, m, s)
        return None
