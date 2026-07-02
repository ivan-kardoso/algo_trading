from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ..domain.errors import EmptyOHLCVError
from ..domain.ports import IMarketDataRepository, IMarketDataSource, OHLCVData
from .transform import OHLCVTransform

if TYPE_CHECKING:
    from loguru import Logger


class MemoryRepository(IMarketDataRepository):
    def __init__(
        self,
        source: IMarketDataSource,
        transform: OHLCVTransform,
        candle_limit: int,
        max_rows: int,
        batch_limit: int,
        fetch_retry_attempts: int,
        fetch_retry_delay: int,
        log: Logger,
    ) -> None:
        self._source = source
        self._transform = transform
        self._candle_limit = candle_limit
        self._max_rows = max_rows
        self._batch_limit = batch_limit
        self._fetch_retry_attempts = fetch_retry_attempts
        self._fetch_retry_delay = fetch_retry_delay
        self._log = log
        self._dataset: OHLCVData = []

    def get_dataset(self) -> OHLCVData:
        return self._dataset

    def seconds_until_next_candle(self) -> int:
        timeframe_s = self._source.timeframe_ms // 1000
        now_s = int(datetime.now(timezone.utc).timestamp())
        return timeframe_s - (now_s % timeframe_s)

    async def _fetch_with_empty_retry(
        self, since: int | None, limit: int | None
    ) -> OHLCVData:
        for attempt in range(1, self._fetch_retry_attempts + 1):
            candles = await self._source.fetch_ohlcv(since=since, limit=limit)
            if candles:
                return candles
            if attempt < self._fetch_retry_attempts:
                self._log.info(
                    f"Candle indisponível (tentativa {attempt}/"
                    f"{self._fetch_retry_attempts}). "
                    f"Aguardando {self._fetch_retry_delay}s..."
                )
                await asyncio.sleep(self._fetch_retry_delay)

        raise EmptyOHLCVError(
            f"Nenhum candle obtido após {self._fetch_retry_attempts} tentativas."
        )

    async def _download_initial(self) -> OHLCVData:
        return await self._fetch_with_empty_retry(since=None, limit=self._candle_limit)

    async def _download_incremental(self) -> OHLCVData:
        since = int(self._dataset[-1][0]) + 1
        # Primeiro lote com retry: se o candle novo ainda não publicou, tenta
        # novamente (fetch_retry_delay/attempts). Esgotou → EmptyOHLCVError → ERROR.
        first = await self._fetch_with_empty_retry(since=since, limit=self._batch_limit)

        all_candles: OHLCVData = list(first)
        # Continua a paginação a partir do primeiro lote.
        if len(first) < self._batch_limit:
            return all_candles
        since = int(first[-1][0]) + self._source.timeframe_ms

        while True:
            batch = await self._source.fetch_ohlcv(since=since, limit=self._batch_limit)
            if not batch:
                break
            all_candles.extend(batch)
            if len(batch) < self._batch_limit:
                break
            since = int(batch[-1][0]) + self._source.timeframe_ms

        return all_candles

    def _merge_and_trim(self, new_candles: OHLCVData) -> None:
        seen: dict[int, list] = {}
        for row in self._dataset + new_candles:
            seen[int(row[0])] = row
        merged = [seen[ts] for ts in sorted(seen)]
        self._dataset = merged[-self._max_rows :] if self._max_rows else merged

    async def update(self) -> None:
        if not self._dataset:
            candles = await self._download_initial()
        else:
            candles = await self._download_incremental()

        self._transform.validate(candles, self._source.timeframe_ms)
        self._merge_and_trim(candles)
        self._log.info(f"Dataset atualizado: {len(self._dataset)} candles.")
