from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Literal


class IOrderExecutor(ABC):
    @abstractmethod
    async def open_order(self, side: Literal["buy", "sell"]) -> dict[str, Any]: ...

    @abstractmethod
    async def cancel_all_orders(self) -> None: ...
