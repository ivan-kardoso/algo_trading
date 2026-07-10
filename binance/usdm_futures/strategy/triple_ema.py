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

    def apply_indicators(self, datasets: dict[str, OHLCVData]) -> dict[str, IndicatorData]:
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

    def _check_alignment(self, role: str, f: float, m: float, s: float) -> Literal["buy", "sell"] | None:
        alignment: Literal["buy", "sell"] | None = "buy" if f > m > s else "sell" if f < m < s else None

        previous = self._last_alignment.get(role, "init")
        if alignment != previous:
            timeframe = self._timeframes.get(role, role)
            if alignment == "buy":
                self._log.log("TREND", f"timeframe {timeframe} Alinhamento EMA para compra.")
            elif alignment == "sell":
                self._log.log("TREND", f"timeframe {timeframe} Alinhamento EMA para venda.")
            else:
                self._log.log("TREND", f"timeframe {timeframe} EMA sem alinhamento.")

            self._last_alignment[role] = alignment

        return alignment

    def _is_trend_aligned(self, indicators: dict[str, IndicatorData]) -> Literal["buy", "sell"] | None:
        trend = indicators.get("trend")
        if trend is None:
            return None

        i = len(trend.candles) - 1
        if i < 0:
            return None

        f = trend.ema_fast[i]
        m = trend.ema_medium[i]
        s = trend.ema_slow[i]
        if f is None or m is None or s is None:
            return None

        return self._check_alignment("trend", f, m, s)

    def _is_signal_aligned(self, indicators: dict[str, IndicatorData]) -> Literal["buy", "sell"] | None:
        signal = indicators.get("signal")
        if signal is None:
            return None

        i = len(signal.candles) - 1
        if i < 0:
            return None

        f = signal.ema_fast[i]
        m = signal.ema_medium[i]
        s = signal.ema_slow[i]
        if f is None or m is None or s is None:
            return None

        return self._check_alignment("signal", f, m, s)

    def check_signal(self, indicators: dict[str, IndicatorData]) -> Literal["buy", "sell"] | None:
        trend_side = self._is_trend_aligned(indicators)
        if trend_side is None:
            return None

        signal_side = self._is_signal_aligned(indicators)
        if signal_side is None:
            return None

        # Trend alinhado (trend_side = "buy" ou "sell").
        # O resto da estratégia vem aqui depois.
        return None
