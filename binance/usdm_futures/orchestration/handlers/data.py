"""Handler de dados: FETCH_DATA."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ...domain.ports import IMarketDataRepository
from ...domain.state_machine.transitions import FetchDataEvent, RunContext

if TYPE_CHECKING:
    from loguru import Logger


def _trend_candle_closed(trend_repo: IMarketDataRepository, last_trend_ts: int | None) -> bool:
    """True se um novo candle de trend fechou desde `last_trend_ts`.

    `last_trend_ts` None significa que o trend ainda não foi baixado
    (download inicial), então sempre é considerado "fechado" para forçar
    a primeira atualização.
    """
    if last_trend_ts is None:
        return True

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    current_bucket = (now_ms // trend_repo.timeframe_ms) * trend_repo.timeframe_ms
    return current_bucket > last_trend_ts


async def handle_fetch_data(
    ctx: RunContext,
    signal_repo: IMarketDataRepository,
    trend_repo: IMarketDataRepository,
    last_trend_ts: int | None,
    symbol: str,
    log: Logger,
) -> tuple[FetchDataEvent, int | None]:
    """Atualiza os datasets OHLCV em memória via repositories.

    O dataset de signal é atualizado sempre. O dataset de trend só é
    atualizado quando um novo candle de trend fechou desde `last_trend_ts`
    (ou no download inicial, quando `last_trend_ts` ainda é None).
    """
    if not ctx.has_exchange:
        log.error(f"[{symbol}] Conexão com exchange ausente. ERROR STATE.")
        return FetchDataEvent.DEPS_MISSING, last_trend_ts

    try:
        await signal_repo.update()
        log.info(f"[{symbol}] Dataset atualizado.")

        if _trend_candle_closed(trend_repo, last_trend_ts):
            await trend_repo.update()
            last_trend_ts = int(trend_repo.get_dataset()[-1][0])
            log.info(f"[{symbol}] Dataset de tendência atualizado.")

        return FetchDataEvent.SUCCESS, last_trend_ts
    except Exception as exc:
        log.error(f"[{symbol}] Erro ao atualizar dataset: {exc}")
        return FetchDataEvent.ERROR, last_trend_ts
