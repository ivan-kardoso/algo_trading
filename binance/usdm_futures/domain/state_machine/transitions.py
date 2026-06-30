"""Regras puras de transição da FSM — sem I/O, sem side effects.

Cada `on_*` recebe o contexto mutável e o evento produzido pelo handler
correspondente, atualiza contadores e determina o próximo estado. O handler
(orchestration/) realiza o I/O e emite o evento correto; a transição decide
onde a máquina vai a seguir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

from .states import State, StandbyReason


# ---------------------------------------------------------------------------
# Eventos de resultado — emitidos pelos handlers (orchestration/)
# ---------------------------------------------------------------------------

class GetPairEvent(Enum):
    ALREADY_LOADED = "already_loaded"  # símbolo já estava em ctx
    LOADED = "loaded"                  # carregado com sucesso agora
    ERROR = "error"                    # falha ao carregar TOML


class ExchangeEvent(Enum):
    CONNECTED = "connected"
    ERROR = "error"


class ManageOrdersEvent(Enum):
    ALREADY_READY = "already_ready"  # execução já inicializada
    INITIALIZED = "initialized"      # inicializada agora
    FATAL = "fatal"                  # BadRequest/Auth → STOPPED + TOML inválido
    DEPS_MISSING = "deps_missing"    # símbolo ou conexão ausente
    ERROR = "error"                  # falha transitória → ERROR


class CleanOrphansEvent(Enum):
    DEPS_MISSING = "deps_missing"       # execução não inicializada
    CHECK_ERROR = "check_error"         # has_active_position retornou None
    HAS_POSITION = "has_position"       # posição ativa + proteção normalizada
    NO_POSITION = "no_position"         # sem posição + estado normalizado
    NORMALIZE_ERROR = "normalize_error" # normalize_position_state retornou None


class FetchDataEvent(Enum):
    SUCCESS = "success"
    DEPS_MISSING = "deps_missing"
    ERROR = "error"


class ApplyStrategyEvent(Enum):
    HAS_DATA = "has_data"
    EMPTY = "empty"  # dataset vazio → STANDBY


class CheckSignalEvent(Enum):
    BUY = "buy"
    SELL = "sell"
    NO_SIGNAL = "no_signal"
    NO_DATA = "no_data"  # dataset None → STANDBY


class OpeningPositionEvent(Enum):
    DEPS_MISSING = "deps_missing"   # orders/signal ausentes → ERROR
    ALREADY_OPEN = "already_open"   # posição já ativa → MONITORING
    CHECK_FAILED = "check_failed"   # has_active_position retornou None → STANDBY
    SUCCESS = "success"             # posição aberta com sucesso → MONITORING
    OPEN_FAILED = "open_failed"     # open_order success=False → STANDBY


class MonitoringEvent(Enum):
    DEPS_MISSING = "deps_missing"   # orders não inicializado → ERROR
    STILL_ACTIVE = "still_active"   # posição ativa → permanece em MONITORING
    CHECK_FAILED = "check_failed"   # has_active_position retornou None
    CLOSED = "closed"               # posição encerrada → CLEAN_ORDERS_ORPHANS


# ---------------------------------------------------------------------------
# Contexto mutável da FSM
# ---------------------------------------------------------------------------

@dataclass
class RunContext:
    """Contexto mutável da máquina de estados de um par.

    Contém apenas dados de controle do fluxo — sem objetos de infraestrutura
    (conexão, execução, dados). Aqueles são gerenciados pelo symbol_runner.
    """

    # Estado atual
    state: State = field(default=State.CHECK_WINDOW)

    # Standby
    standby_reason: StandbyReason | None = None
    standby_next_state: State | None = None

    # Flags de inicialização (gerenciadas pelo symbol_runner)
    has_symbol: bool = False
    has_exchange: bool = False
    has_execution: bool = False
    has_data_pipeline: bool = False

    # Sinal de entrada detectado
    signal_side: Literal["buy", "sell"] | None = None

    # Contadores de retry/falha
    cleanup_retries: int = 0
    error_retries: int = 0
    monitoring_failures: int = 0
    monitoring_check_count: int = 0

    # Limites de retry/falha (vindos de SystemSettings.monitoring)
    max_cleanup_retries: int = 3
    max_error_retries: int = 3
    max_monitoring_failures: int = 10
    monitoring_heartbeat_every: int = 20


# ---------------------------------------------------------------------------
# Funções puras de transição
# ---------------------------------------------------------------------------

def on_check_window(ctx: RunContext, market_open: bool) -> None:
    """CHECK_WINDOW: verifica se o mercado está dentro da janela operacional."""
    if market_open:
        ctx.state = State.GET_PAIR
    else:
        ctx.standby_reason = StandbyReason.MARKET_CLOSED
        ctx.state = State.STANDBY


def on_get_pair(ctx: RunContext, event: GetPairEvent) -> None:
    """GET_PAIR: carrega o par do arquivo TOML.

    Se já carregado, verifica apenas se a conexão existe para decidir
    entre EXCHANGE e MANAGE_ORDERS.
    """
    if event == GetPairEvent.ERROR:
        ctx.state = State.ERROR
        return
    # LOADED ou ALREADY_LOADED
    ctx.has_symbol = True
    ctx.state = State.MANAGE_ORDERS if ctx.has_exchange else State.EXCHANGE


def on_exchange(ctx: RunContext, event: ExchangeEvent) -> None:
    """EXCHANGE: cria a conexão com a exchange."""
    if event == ExchangeEvent.CONNECTED:
        ctx.has_exchange = True
        ctx.state = State.MANAGE_ORDERS
    else:
        ctx.state = State.ERROR


def on_manage_orders(ctx: RunContext, event: ManageOrdersEvent) -> None:
    """MANAGE_ORDERS: inicializa os módulos de execução (tracker, executor, protection).

    BadRequest/AuthenticationError em initialize() → STOPPED (configura
    TOML como inválido no handler). Erros transitórios → ERROR para retry.
    """
    if event == ManageOrdersEvent.FATAL:
        ctx.state = State.STOPPED
        return
    if event in (ManageOrdersEvent.ERROR, ManageOrdersEvent.DEPS_MISSING):
        ctx.has_execution = False
        ctx.state = State.ERROR
        return
    # ALREADY_READY ou INITIALIZED
    ctx.has_execution = True
    ctx.error_retries = 0
    ctx.state = State.CLEAN_ORDERS_ORPHANS


def on_clean_orphans(ctx: RunContext, event: CleanOrphansEvent) -> None:
    """CLEAN_ORDERS_ORPHANS: verifica/normaliza posições e ordens órfãs.

    Retry de CHECK_ERROR: até max_cleanup_retries tentativas voltando a
    CHECK_WINDOW. Se esgotar → ERROR. Falha em normalize → ERROR imediato
    (posição exposta, humano deve investigar).
    """
    if event == CleanOrphansEvent.DEPS_MISSING:
        ctx.state = State.MANAGE_ORDERS
        return

    if event == CleanOrphansEvent.CHECK_ERROR:
        ctx.cleanup_retries += 1
        if ctx.cleanup_retries >= ctx.max_cleanup_retries:
            ctx.cleanup_retries = 0
            ctx.state = State.ERROR
        else:
            ctx.state = State.CHECK_WINDOW
        return

    # has_active_position retornou não-None → reset de cleanup_retries
    ctx.cleanup_retries = 0

    if event == CleanOrphansEvent.NORMALIZE_ERROR:
        ctx.state = State.ERROR
        return

    ctx.error_retries = 0
    ctx.state = (
        State.MONITORING
        if event == CleanOrphansEvent.HAS_POSITION
        else State.FETCH_DATA
    )


def on_fetch_data(ctx: RunContext, event: FetchDataEvent) -> None:
    """FETCH_DATA: baixa e atualiza os candles do par em memória."""
    if event in (FetchDataEvent.DEPS_MISSING, FetchDataEvent.ERROR):
        ctx.state = State.ERROR
        return
    ctx.has_data_pipeline = True
    ctx.error_retries = 0
    ctx.state = State.APPLY_STRATEGY


def on_apply_strategy(ctx: RunContext, event: ApplyStrategyEvent) -> None:
    """APPLY_STRATEGY: calcula indicadores técnicos sobre o dataset."""
    if event == ApplyStrategyEvent.EMPTY:
        ctx.standby_reason = StandbyReason.WAIT_NEXT_CANDLE
        ctx.standby_next_state = State.FETCH_DATA
        ctx.state = State.STANDBY
        return
    ctx.state = State.CHECK_SIGNAL


def on_check_signal(ctx: RunContext, event: CheckSignalEvent) -> None:
    """CHECK_SIGNAL: consulta a estratégia para decidir entrada."""
    if event in (CheckSignalEvent.NO_DATA, CheckSignalEvent.NO_SIGNAL):
        ctx.standby_reason = StandbyReason.WAIT_NEXT_CANDLE
        ctx.standby_next_state = State.FETCH_DATA
        ctx.state = State.STANDBY
        return
    ctx.signal_side = event.value  # "buy" ou "sell"
    ctx.state = State.OPENING_POSITION


def on_opening_position(ctx: RunContext, event: OpeningPositionEvent) -> None:
    """OPENING_POSITION: abre posição baseada no sinal detectado.

    Se posição já ativa (ALREADY_OPEN), vai direto para MONITORING sem abrir
    nova entrada. Se verificação falhar (CHECK_FAILED) ou abertura falhar
    (OPEN_FAILED), vai para STANDBY aguardando próximo candle.
    """
    if event == OpeningPositionEvent.DEPS_MISSING:
        ctx.state = State.ERROR
        return

    if event == OpeningPositionEvent.ALREADY_OPEN:
        ctx.signal_side = None
        ctx.state = State.MONITORING
        return

    if event in (OpeningPositionEvent.CHECK_FAILED, OpeningPositionEvent.OPEN_FAILED):
        ctx.signal_side = None
        ctx.standby_reason = StandbyReason.WAIT_NEXT_CANDLE
        ctx.standby_next_state = State.FETCH_DATA
        ctx.state = State.STANDBY
        return

    # SUCCESS
    ctx.signal_side = None
    ctx.error_retries = 0
    ctx.state = State.MONITORING


def on_monitoring(ctx: RunContext, event: MonitoringEvent) -> None:
    """MONITORING: monitora posição ativa até encerramento.

    CHECK_FAILED acumula falhas consecutivas; ao atingir max_monitoring_failures
    vai para ERROR (5 minutos de tolerância com sleep de 30s entre checks).
    STILL_ACTIVE reseta o contador de falhas e acumula o check_count para
    heartbeat. CLOSED inicia o ciclo de limpeza.
    """
    if event == MonitoringEvent.DEPS_MISSING:
        ctx.monitoring_failures = 0
        ctx.monitoring_check_count = 0
        ctx.state = State.ERROR
        return

    if event == MonitoringEvent.CHECK_FAILED:
        ctx.monitoring_failures += 1
        if ctx.monitoring_failures >= ctx.max_monitoring_failures:
            ctx.monitoring_failures = 0
            ctx.monitoring_check_count = 0
            ctx.state = State.ERROR
        # se abaixo do limite, permanece em MONITORING (handler re-entra)
        return

    if event == MonitoringEvent.STILL_ACTIVE:
        ctx.monitoring_failures = 0
        ctx.monitoring_check_count += 1
        # permanece em MONITORING
        return

    # CLOSED
    ctx.monitoring_failures = 0
    ctx.monitoring_check_count = 0
    ctx.error_retries = 0
    ctx.state = State.CLEAN_ORDERS_ORPHANS


def on_standby(ctx: RunContext) -> None:
    """STANDBY: aguarda conforme o motivo (handler realizou o sleep).

    Após o sleep, MARKET_CLOSED volta sempre para CHECK_WINDOW.
    WAIT_NEXT_CANDLE vai para standby_next_state (ou FETCH_DATA como fallback).
    """
    if ctx.standby_reason == StandbyReason.MARKET_CLOSED:
        next_state = State.CHECK_WINDOW
    else:
        next_state = ctx.standby_next_state or State.FETCH_DATA

    ctx.standby_reason = None
    ctx.standby_next_state = None
    ctx.state = next_state


def on_error(ctx: RunContext) -> None:
    """ERROR: tenta recuperar com retry até max_error_retries → STOPPED.

    O handler dorme error_wait_seconds antes de chamar on_error, de modo
    que ao sair daqui o contexto já aponta para o próximo estado.
    """
    ctx.error_retries += 1
    if ctx.error_retries >= ctx.max_error_retries:
        ctx.state = State.STOPPED
    else:
        ctx.state = State.CHECK_WINDOW


# ---------------------------------------------------------------------------
# Utilitário de consulta (sem mutação)
# ---------------------------------------------------------------------------

def is_heartbeat_due(ctx: RunContext) -> bool:
    """True se o check_count atingiu o múltiplo de heartbeat configurado."""
    return (
        ctx.monitoring_check_count > 0
        and ctx.monitoring_check_count % ctx.monitoring_heartbeat_every == 0
    )
