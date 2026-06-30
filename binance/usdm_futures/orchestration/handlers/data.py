"""Handler de dados: FETCH_DATA."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.ports import IMarketDataRepository
from ...domain.state_machine.transitions import FetchDataEvent, RunContext

if TYPE_CHECKING:
    from loguru import Logger


async def handle_fetch_data(
    ctx: RunContext,
    repo: IMarketDataRepository,
    symbol: str,
    log: Logger,
) -> FetchDataEvent:
    """Atualiza o dataset OHLCV em memória via repository."""
    if not ctx.has_exchange:
        log.error(f"[{symbol}] Conexão com exchange ausente. ERROR STATE.")
        return FetchDataEvent.DEPS_MISSING

    try:
        await repo.update()
        log.info(f"[{symbol}] Dataset atualizado.")
        return FetchDataEvent.SUCCESS
    except Exception as exc:
        log.error(f"[{symbol}] Erro ao atualizar dataset: {exc}")
        return FetchDataEvent.ERROR
