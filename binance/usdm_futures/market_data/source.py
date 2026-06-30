from __future__ import annotations

from typing import TYPE_CHECKING

import ccxt.async_support as ccxt

from ..domain.ports import IMarketDataSource, OHLCVData
from ..infrastructure.errors import translate_ccxt_error

if TYPE_CHECKING:
    from loguru import Logger


class OHLCVSource(IMarketDataSource):
    def __init__(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: str,
        log: Logger,
    ) -> None:
        self._exchange = exchange
        self._symbol = symbol
        self._timeframe = timeframe
        self._log = log
        self._timeframe_ms: int = int(exchange.parse_timeframe(timeframe) * 1000)

    @property
    def timeframe_ms(self) -> int:
        return self._timeframe_ms

    async def fetch_ohlcv(
        self,
        since: int | None = None,
        limit: int | None = None,
    ) -> OHLCVData:
        try:
            candles = await self._exchange.fetch_ohlcv(
                symbol=self._symbol,
                timeframe=self._timeframe,
                since=since,
                limit=limit,
            )
            return candles or []
        except Exception as exc:
            raise translate_ccxt_error(exc) from exc
