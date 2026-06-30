from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from . import OHLCVData


class IStrategyPort(ABC):
    @abstractmethod
    def apply_indicators(self, data: OHLCVData) -> OHLCVData: ...

    @abstractmethod
    def check_signal(self, data: OHLCVData) -> Literal["buy", "sell"] | None: ...
