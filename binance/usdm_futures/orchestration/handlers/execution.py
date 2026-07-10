"""Handler de execução: OPENING_POSITION."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.ports import IOrderExecutor, IPositionTracker
from ...domain.state_machine.transitions import OpeningPositionEvent, RunContext

if TYPE_CHECKING:
    from loguru import Logger


async def handle_opening_position(
    ctx: RunContext,
    tracker: IPositionTracker,
    executor: IOrderExecutor,
    symbol: str,
    log: Logger,
) -> tuple[OpeningPositionEvent, float | None]:
    """Abre posição baseada no sinal detectado.

    Retorna (event, entry_price). entry_price é não-None apenas em SUCCESS.

    Fluxo:
    - Dependências ausentes → DEPS_MISSING (→ ERROR)
    - Posição já ativa → ALREADY_OPEN (→ MONITORING sem nova entrada)
    - Falha ao verificar posição → CHECK_FAILED (→ STANDBY)
    - open_order success=True → SUCCESS (→ MONITORING)
    - open_order success=False → OPEN_FAILED (→ STANDBY)
    """
    if not ctx.has_execution or ctx.signal_side is None:
        log.error(f"[{symbol}] Dependências de execução ausentes. ERROR STATE.")
        return OpeningPositionEvent.DEPS_MISSING, None

    has_position = await tracker.has_active_position()

    if has_position is True:
        log.warning(f"[{symbol}] Posição já ativa. Cancelando entrada. MONITORING STATE.")
        return OpeningPositionEvent.ALREADY_OPEN, None

    if has_position is None:
        log.warning(f"[{symbol}] Falha ao verificar posição. Cancelando entrada. STANDBY.")
        return OpeningPositionEvent.CHECK_FAILED, None

    side = ctx.signal_side
    log.log("POS_OPEN", f"[{symbol}] Abrindo posição: {side.upper()}...")

    result = await executor.open_order(side=side)

    if result.get("success"):
        entry_price: float | None = result.get("entry_price")
        log.log("POS_OPEN", f"[{symbol}] Posição aberta! Preço: {entry_price:.8g}" if entry_price else f"[{symbol}] Posição aberta!")
        return OpeningPositionEvent.SUCCESS, entry_price

    log.warning(f"[{symbol}] Falha ao abrir posição.")
    return OpeningPositionEvent.OPEN_FAILED, None
