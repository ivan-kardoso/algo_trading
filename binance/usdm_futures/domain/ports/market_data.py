from __future__ import annotations

from abc import ABC, abstractmethod

from . import OHLCVData


class IMarketDataSource(ABC):
    """Abstração para busca de candles OHLCV na exchange."""

    @abstractmethod
    async def fetch_ohlcv(
        self,
        since: int | None = None,
        limit: int | None = None,
    ) -> OHLCVData: ...

    @property
    @abstractmethod
    def timeframe_ms(self) -> int: ...


class IMarketDataRepository(ABC):
    """Armazena e expõe o dataset OHLCV em memória para a orquestração."""

    @abstractmethod
    async def update(self) -> None: ...

    @abstractmethod
    def get_dataset(self) -> OHLCVData: ...

    @abstractmethod
    def last_candle_ts(self) -> int | None: ...

    @abstractmethod
    def seconds_until_next_candle(self) -> int: ...

    @abstractmethod
    def candle_count(self) -> int: ...

    @property
    @abstractmethod
    def timeframe_ms(self) -> int: ...
