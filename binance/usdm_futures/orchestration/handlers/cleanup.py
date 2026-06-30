"""Handler de limpeza: CLEAN_ORDERS_ORPHANS."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.ports import IPositionTracker
from ...domain.state_machine.transitions import CleanOrphansEvent, RunContext

if TYPE_CHECKING:
    from loguru import Logger


async def handle_clean_orphans(
    ctx: RunContext,
    tracker: IPositionTracker,
    symbol: str,
    log: Logger,
) -> CleanOrphansEvent:
    """Verifica posições e ordens órfãs e normaliza o estado.

    has_active_position → None: erro transitório, retorna CHECK_ERROR para
    que on_clean_orphans acumule retries e eventualmente vá para ERROR.
    Se há posição: normalize_position_state confirma proteção → MONITORING.
    Se não há: normalize_position_state cancela não-proteção → FETCH_DATA.
    Normalize → None em qualquer dos casos: ERROR imediato (posição exposta).
    """
    if not ctx.has_execution:
        log.warning(f"[{symbol}] Módulos de execução não inicializados. MANAGE_ORDERS.")
        return CleanOrphansEvent.DEPS_MISSING

    log.info(f"[{symbol}] Verificando posições e ordens órfãs...")

    has_position = await tracker.has_active_position()

    if has_position is None:
        next_retries = ctx.cleanup_retries + 1
        log.warning(
            f"[{symbol}] Falha ao verificar posição. "
            f"Tentativa {next_retries}/{ctx.max_cleanup_retries}."
        )
        return CleanOrphansEvent.CHECK_ERROR

    if has_position:
        log.info(f"[{symbol}] Posição ativa encontrada. Verificando proteção...")
    else:
        log.info(f"[{symbol}] Sem posição ativa. Normalizando ordens pendentes...")

    normalized = await tracker.normalize_position_state()

    if normalized is None:
        log.critical(
            f"[{symbol}] Proteção não pôde ser confirmada. "
            f"Posição permanece exposta. ERROR STATE."
        )
        return CleanOrphansEvent.NORMALIZE_ERROR

    if has_position:
        log.info(f"[{symbol}] Posição protegida. Indo para MONITORING.")
        return CleanOrphansEvent.HAS_POSITION

    log.info(f"[{symbol}] Estado normalizado. Indo para FETCH_DATA.")
    return CleanOrphansEvent.NO_POSITION
