from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal


class IProtectionOrders(ABC):
    @abstractmethod
    async def send_protection_orders(
        self,
        side: Literal["buy", "sell"],
        entry_price: float,
        amount: float | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]: ...

    @abstractmethod
    async def recreate_missing(
        self,
        side: Literal["buy", "sell"],
        entry_price: float,
        has_sl: bool,
        has_tp: bool,
        amount: float,
    ) -> tuple[bool, bool]: ...
