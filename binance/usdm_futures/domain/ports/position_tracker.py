from __future__ import annotations

from abc import ABC, abstractmethod


class IPositionTracker(ABC):
    @abstractmethod
    async def initialize(self) -> None: ...

    @abstractmethod
    async def has_active_position(self) -> bool | None: ...

    @abstractmethod
    async def normalize_position_state(self) -> bool | None: ...
