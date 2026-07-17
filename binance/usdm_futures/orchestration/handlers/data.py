"""Handler de dados: FETCH_DATA."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ...domain.models.timeframe_slot import TimeframeSlot
from ...domain.ports import IMarketDataRepository
from ...domain.state_machine.transitions import FetchDataEvent, RunContext

if TYPE_CHECKING:
    from loguru import Logger


def _candle_closed(repo: IMarketDataRepository) -> bool:
    """True se um novo candle já fechou desde o último candle conhecido do repo.

    Sem dataset ainda (download inicial) é sempre considerado "fechado",
    para forçar a primeira atualização.
    """
    last_ts = repo.last_candle_ts()
    if last_ts is None:
        return True

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    current_bucket = (now_ms // repo.timeframe_ms) * repo.timeframe_ms
    return current_bucket - repo.timeframe_ms > last_ts


async def handle_fetch_data(
    ctx: RunContext,
    rhythm_repo: IMarketDataRepository,
    rhythm_slot: TimeframeSlot,
    other_repos: dict[TimeframeSlot, IMarketDataRepository],
    timeframes: dict[TimeframeSlot, str],
    symbol: str,
    log: Logger,
) -> FetchDataEvent:
    """Atualiza os datasets OHLCV em memória via repositories.

    O dataset da posição de ritmo (informada pela estratégia) é atualizado
    sempre. Cada dataset em `other_repos` (as demais posições preenchidas)
    só é atualizado quando um candle novo daquele timeframe fechou desde a
    última atualização (ou no download inicial).
    """
    if not ctx.has_exchange:
        log.error(f"[{symbol}] Conexão com exchange ausente. ERROR STATE.")
        return FetchDataEvent.DEPS_MISSING

    try:
        updated: list[str] = []

        await rhythm_repo.update()
        updated.append(f"{timeframes[rhythm_slot]} ({rhythm_repo.candle_count()})")

        for slot, repo in other_repos.items():
            if _candle_closed(repo):
                await repo.update()
                updated.append(f"{timeframes[slot]} ({repo.candle_count()})")

        log.log("DATASET", f"[{symbol}] Datasets atualizados: {' | '.join(updated)}")

        return FetchDataEvent.SUCCESS
    except Exception as exc:
        log.error(f"[{symbol}] Erro ao atualizar dataset: {exc}")
        return FetchDataEvent.ERROR
