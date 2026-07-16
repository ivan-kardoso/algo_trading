from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..ports import OHLCVData


@dataclass(frozen=True)
class IndicatorData:
    candles: OHLCVData
    ema_fast: list[float | None]
    ema_medium: list[float | None]
    ema_slow: list[float | None]


@dataclass
class MACDResult:
    macd: list[Optional[float | None]]
    signal: list[Optional[float | None]]
    histogram: list[Optional[float | None]]
