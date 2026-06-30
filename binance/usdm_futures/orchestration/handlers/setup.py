"""Handlers de inicialização: GET_PAIR, EXCHANGE, MANAGE_ORDERS."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.errors import AuthenticationError, BadRequestError
from ...domain.ports import IPositionTracker
from ...domain.state_machine.transitions import (
    ExchangeEvent,
    GetPairEvent,
    ManageOrdersEvent,
    RunContext,
)
from ...infrastructure.exchange_client import ExchangeClient
from ...shared.helpers import mark_toml_as_invalid

if TYPE_CHECKING:
    from loguru import Logger


def handle_get_pair(ctx: RunContext, symbol: str) -> GetPairEvent:
    """Verifica se o símbolo já está no contexto.

    No novo sistema, o símbolo é pré-carregado pelo bootstrap — esta
    função apenas confirma o estado para acionar a transição correta.
    """
    if ctx.has_symbol:
        return GetPairEvent.ALREADY_LOADED
    # Nunca deve ocorrer se bootstrap inicializou ctx corretamente.
    return GetPairEvent.ERROR


async def handle_exchange(
    client: ExchangeClient,
    symbol: str,
    log: Logger,
) -> ExchangeEvent:
    """Conecta o client à exchange e valida a sessão."""
    try:
        await client.connect()
        log.info(f"[{symbol}] Conexão com a exchange estabelecida.")
        return ExchangeEvent.CONNECTED
    except Exception as exc:
        log.error(f"[{symbol}] Falha na conexão: {exc}")
        return ExchangeEvent.ERROR


async def handle_manage_orders(
    ctx: RunContext,
    tracker: IPositionTracker,
    symbol: str,
    toml_path: str,
    log: Logger,
) -> ManageOrdersEvent:
    """Inicializa os módulos de execução via PositionTracker.initialize().

    BadRequest/AuthenticationError indica configuração incompatível com a
    conta (par inválido, leverage acima do permitido, credencial errada) —
    TOML é marcado como inválido e o par para definitivamente (STOPPED).

    Erros transitórios resultam em ERROR para retry via ciclo normal.
    """
    if ctx.has_execution:
        return ManageOrdersEvent.ALREADY_READY

    if not ctx.has_exchange or not ctx.has_symbol:
        log.error(f"[{symbol}] Dependências ausentes (exchange/símbolo). ERROR STATE.")
        return ManageOrdersEvent.DEPS_MISSING

    log.info(f"[{symbol}] Inicializando módulos de execução...")

    try:
        await tracker.initialize()
    except (BadRequestError, AuthenticationError) as exc:
        log.critical(
            f"[{symbol}] Configuração inválida para esta conta: {exc}. "
            f"TOML: {toml_path}. STOPPED."
        )
        try:
            invalid_path = mark_toml_as_invalid(toml_path)
            log.critical(f"[{symbol}] TOML renomeado para: {invalid_path}")
        except Exception as rename_exc:
            log.error(f"[{symbol}] Falha ao renomear TOML: {rename_exc}")
        return ManageOrdersEvent.FATAL
    except Exception as exc:
        log.warning(f"[{symbol}] Falha transitória em initialize: {exc}. ERROR STATE.")
        return ManageOrdersEvent.ERROR

    log.info(f"[{symbol}] Módulos de execução prontos.")
    return ManageOrdersEvent.INITIALIZED
