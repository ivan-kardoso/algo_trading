"""Handlers de fluxo: CHECK_WINDOW, STANDBY, ERROR."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ...domain.ports import IMarketDataRepository
from ...domain.state_machine.transitions import RunContext, StandbyReason
from ...shared.market_hours import MarketHoursChecker

if TYPE_CHECKING:
    from loguru import Logger


def handle_check_window(hours: MarketHoursChecker) -> bool:
    """Retorna True se o mercado está dentro da janela operacional."""
    return hours.is_market_open()


async def handle_standby(
    ctx: RunContext,
    hours: MarketHoursChecker,
    repo: IMarketDataRepository,
    candle_delay: int,
    log: Logger,
) -> None:
    """Dorme pelo tempo necessário conforme o motivo do standby.

    MARKET_CLOSED: dorme até a próxima abertura.
    WAIT_NEXT_CANDLE: dorme até o próximo candle (+ 5s de margem).
    Se o pipeline ainda não foi inicializado (has_data_pipeline=False),
    não dorme — vai direto para FETCH_DATA.
    """
    if ctx.standby_reason == StandbyReason.MARKET_CLOSED:
        seconds = hours.seconds_until_next_open()
        if seconds <= 0:
            return
        hours_left = seconds // 3600
        minutes_left = (seconds % 3600) // 60
        log.info(
            f"Mercado fechado — aguardando {hours_left}h {minutes_left}min "
            f"até a próxima abertura."
        )
        await asyncio.sleep(seconds)

    else:  # WAIT_NEXT_CANDLE
        if not ctx.has_data_pipeline:
            return  # on_standby vai para FETCH_DATA via fallback
        seconds = repo.seconds_until_next_candle() + candle_delay
        log.info(f"Aguardando próximo candle ({seconds}s)...")
        await asyncio.sleep(seconds)


async def handle_error(
    ctx: RunContext,
    wait_seconds: float,
    symbol: str,
    log: Logger,
) -> None:
    """Loga o retry e dorme antes de retornar para CHECK_WINDOW.

    Não dorme se o próximo incremento vai atingir max_error_retries
    (a transição vai para STOPPED e não precisa de delay).
    """
    next_retries = ctx.error_retries + 1
    if next_retries >= ctx.max_error_retries:
        log.critical(
            f"[{symbol}] Falha após {next_retries} tentativas consecutivas. Encerrando."
        )
    else:
        log.warning(
            f"[{symbol}] Erro detectado. "
            f"Tentativa {next_retries}/{ctx.max_error_retries}. "
            f"Reiniciando em {wait_seconds}s..."
        )
        await asyncio.sleep(wait_seconds)
