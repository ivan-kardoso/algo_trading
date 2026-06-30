"""Handler de monitoramento: MONITORING."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...domain.ports import IOrderExecutor, IPositionTracker
from ...domain.state_machine.transitions import MonitoringEvent, RunContext

if TYPE_CHECKING:
    from loguru import Logger


async def handle_monitoring(
    ctx: RunContext,
    tracker: IPositionTracker,
    executor: IOrderExecutor,
    symbol: str,
    check_interval: float,
    log: Logger,
) -> MonitoringEvent:
    """Verifica a posição ativa e dorme entre ciclos.

    CHECK_FAILED dorme apenas se ainda há tentativas restantes (o próximo
    incremento não vai atingir max_monitoring_failures); se vai atingir,
    não dorme — a transição vai direto para ERROR.

    CLOSED: cancela ordens órfãs e retorna para CLEAN_ORDERS_ORPHANS.
    """
    if not ctx.has_execution:
        log.error(f"[{symbol}] Módulos de execução não inicializados. ERROR STATE.")
        return MonitoringEvent.DEPS_MISSING

    has_position = await tracker.has_active_position()

    if has_position is None:
        next_failures = ctx.monitoring_failures + 1
        log.warning(
            f"[{symbol}] Falha ao verificar posição. "
            f"{next_failures}/{ctx.max_monitoring_failures}."
        )
        if next_failures >= ctx.max_monitoring_failures:
            log.critical(
                f"[{symbol}] Falhas consecutivas esgotadas em MONITORING. ERROR STATE."
            )
        else:
            await asyncio.sleep(check_interval)
        return MonitoringEvent.CHECK_FAILED

    if has_position:
        await asyncio.sleep(check_interval)
        return MonitoringEvent.STILL_ACTIVE

    # Posição encerrada
    log.info(f"[{symbol}] Posição encerrada. Cancelando ordens residuais...")
    try:
        await executor.cancel_all_orders()
    except Exception as exc:
        log.warning(
            f"[{symbol}] Falha ao cancelar ordens após encerramento: {exc}. Prosseguindo."
        )

    return MonitoringEvent.CLOSED
