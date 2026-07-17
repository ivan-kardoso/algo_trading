"""Motor de orquestração de um par: percorre a FSM e delega a handlers."""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Mapping
from typing import TYPE_CHECKING

from ..config.schedule import SystemSettings
from ..domain.models.indicator_data import IndicatorData
from ..domain.models.role import Role
from ..domain.ports import (
    IMarketDataRepository,
    IOrderExecutor,
    IPositionTracker,
    IStrategyPort,
)
from ..domain.state_machine.states import State
from ..domain.state_machine.transitions import (
    FetchDataEvent,
    MonitoringEvent,
    RunContext,
    is_heartbeat_due,
    on_check_window,
    on_clean_orphans,
    on_error,
    on_exchange,
    on_fetch_data,
    on_apply_strategy,
    on_check_signal,
    on_get_pair,
    on_manage_orders,
    on_monitoring,
    on_opening_position,
    on_standby,
)
from ..infrastructure.exchange_client import ExchangeClient
from ..shared.market_hours import MarketHoursChecker
from .handlers import (
    handle_check_window,
    handle_clean_orphans,
    handle_error,
    handle_exchange,
    handle_fetch_data,
    handle_apply_strategy,
    handle_check_signal,
    handle_get_pair,
    handle_manage_orders,
    handle_monitoring,
    handle_opening_position,
    handle_standby,
)

if TYPE_CHECKING:
    from loguru import Logger


class SymbolRunner:
    """Executa a FSM de um par, delegando cada estado ao handler correspondente.

    Não conhece estratégia, exchange ou config diretamente — recebe tudo
    injetado pelo bootstrap. Sua única responsabilidade é percorrer os estados
    e acionar as transições.
    """

    def __init__(
        self,
        symbol: str,
        ctx: RunContext,
        hours_checker: MarketHoursChecker,
        system_settings: SystemSettings,
        toml_path: str,
        exchange_client: ExchangeClient,
        position_tracker: IPositionTracker,
        order_executor: IOrderExecutor,
        repos: Mapping[Role, IMarketDataRepository],
        timeframes: Mapping[Role, str],
        strategy: IStrategyPort,
        log: Logger,
    ) -> None:
        self._symbol = symbol
        self._ctx = ctx
        self._hours = hours_checker
        self._sys = system_settings
        self._toml_path = toml_path
        self._client = exchange_client
        self._tracker = position_tracker
        self._executor = order_executor
        self._repos = repos
        self._signal_repo = repos[Role.SIGNAL]
        self._other_repos = {
            role: repo for role, repo in repos.items() if role != Role.SIGNAL
        }
        self._timeframes = timeframes
        self._strategy = strategy
        self._log = log

        # Estado entre estados (não faz parte do RunContext pois é volátil)
        self._processed: dict[Role, IndicatorData] | None = None
        self._monitoring_started_at: datetime | None = None

    async def run(self) -> None:
        """Loop principal do par — roda até State.STOPPED."""
        self._log.info(f"[{self._symbol}] SymbolRunner iniciado.")

        while self._ctx.state != State.STOPPED:
            try:
                await self._dispatch()
            except Exception as exc:
                self._log.error(
                    f"[{self._symbol}] Erro inesperado no runner: {exc}",
                    exc_info=True,
                )
                self._ctx.state = State.ERROR

        self._log.info(f"[{self._symbol}] SymbolRunner encerrado.")

    async def _dispatch(self) -> None:
        state = self._ctx.state

        if state == State.CHECK_WINDOW:
            await self._step_check_window()
        elif state == State.GET_PAIR:
            await self._step_get_pair()
        elif state == State.EXCHANGE:
            await self._step_exchange()
        elif state == State.MANAGE_ORDERS:
            await self._step_manage_orders()
        elif state == State.CLEAN_ORDERS_ORPHANS:
            await self._step_clean_orphans()
        elif state == State.FETCH_DATA:
            await self._step_fetch_data()
        elif state == State.APPLY_STRATEGY:
            await self._step_apply_strategy()
        elif state == State.CHECK_SIGNAL:
            await self._step_check_signal()
        elif state == State.OPENING_POSITION:
            await self._step_opening_position()
        elif state == State.MONITORING:
            await self._step_monitoring()
        elif state == State.STANDBY:
            await self._step_standby()
        elif state == State.ERROR:
            await self._step_error()

    # -------------------------------------------------------------------------
    # Passos individuais de cada estado
    # -------------------------------------------------------------------------

    async def _step_check_window(self) -> None:
        market_open = handle_check_window(self._hours)
        on_check_window(self._ctx, market_open)

    async def _step_get_pair(self) -> None:
        event = handle_get_pair(self._ctx, self._symbol)
        on_get_pair(self._ctx, event)

    async def _step_exchange(self) -> None:
        event = await handle_exchange(self._client, self._symbol, self._log)
        on_exchange(self._ctx, event)

    async def _step_manage_orders(self) -> None:
        event = await handle_manage_orders(
            self._ctx,
            self._tracker,
            self._symbol,
            self._toml_path,
            self._log,
        )
        on_manage_orders(self._ctx, event)

    async def _step_clean_orphans(self) -> None:
        event = await handle_clean_orphans(
            self._ctx,
            self._tracker,
            self._symbol,
            self._log,
        )
        on_clean_orphans(self._ctx, event)

    async def _step_fetch_data(self) -> None:
        event = await handle_fetch_data(
            self._ctx,
            self._signal_repo,
            self._other_repos,
            self._timeframes,
            self._symbol,
            self._log,
        )
        on_fetch_data(self._ctx, event)
        if event != FetchDataEvent.SUCCESS:
            self._processed = None

    async def _step_apply_strategy(self) -> None:
        event, processed = handle_apply_strategy(
            self._strategy,
            self._repos,
            self._symbol,
            self._log,
        )
        self._processed = processed
        on_apply_strategy(self._ctx, event)

    async def _step_check_signal(self) -> None:
        event = handle_check_signal(
            self._strategy,
            self._processed,
            self._symbol,
            self._log,
        )
        on_check_signal(self._ctx, event)

    async def _step_opening_position(self) -> None:
        event, entry_price = await handle_opening_position(
            self._ctx,
            self._tracker,
            self._executor,
            self._symbol,
            self._log,
        )
        on_opening_position(self._ctx, event)

        if self._ctx.state == State.MONITORING:
            self._monitoring_started_at = datetime.now(timezone.utc)

    async def _step_monitoring(self) -> None:
        check_interval = float(self._sys.monitoring.monitoring_check_interval_seconds)

        if self._monitoring_started_at is None:
            self._monitoring_started_at = datetime.now(timezone.utc)
            self._log.info(f"[{self._symbol}] Monitorando posição...")

        event = await handle_monitoring(
            self._ctx,
            self._tracker,
            self._executor,
            self._symbol,
            check_interval,
            self._log,
        )
        on_monitoring(self._ctx, event)

        if event == MonitoringEvent.STILL_ACTIVE and is_heartbeat_due(self._ctx):
            active_s = int(
                (datetime.now(timezone.utc) - self._monitoring_started_at).total_seconds()
            )
            active_min = active_s // 60
            self._log.info(
                f"[{self._symbol}] Monitorando (heartbeat): "
                f"{self._ctx.monitoring_check_count} verificações ok, "
                f"ativo há {active_min}min."
            )

        if self._ctx.state != State.MONITORING:
            self._monitoring_started_at = None

    async def _step_standby(self) -> None:
        await handle_standby(
            self._ctx,
            self._hours,
            self._signal_repo,
            self._sys.fetch.candle_fetch_delay_seconds,
            self._log,
        )
        on_standby(self._ctx)

    async def _step_error(self) -> None:
        wait_seconds = float(self._sys.monitoring.error_wait_seconds)
        await handle_error(self._ctx, wait_seconds, self._symbol, self._log)
        on_error(self._ctx)
