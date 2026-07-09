"""Handlers de estratégia: APPLY_STRATEGY, CHECK_SIGNAL."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ...domain.models.indicator_data import IndicatorData
from ...domain.ports import IMarketDataRepository, IStrategyPort
from ...domain.state_machine.transitions import (
    ApplyStrategyEvent,
    CheckSignalEvent,
)

if TYPE_CHECKING:
    from loguru import Logger


def handle_apply_strategy(
    strategy: IStrategyPort,
    trend_repo: IMarketDataRepository,
    signal_repo: IMarketDataRepository,
    symbol: str,
    log: Logger,
) -> tuple[ApplyStrategyEvent, IndicatorData | None, IndicatorData | None]:
    """Aplica indicadores aos datasets de trend e signal.

    Retorna (event, trend_processado, signal_processado). Os datasets
    processados são passados adiante ao handle_check_signal pelo runner;
    nunca persistem em disco.
    """
    trend_data = trend_repo.get_dataset()
    signal_data = signal_repo.get_dataset()
    if not trend_data or not signal_data:
        log.info(f"[{symbol}] Dataset vazio. Aguardando próximo candle.")
        return ApplyStrategyEvent.EMPTY, None, None

    trend_processed, signal_processed = strategy.apply_indicators(trend_data, signal_data)
    log.info(f"[{symbol}] Indicadores calculados.")
    return ApplyStrategyEvent.HAS_DATA, trend_processed, signal_processed


def handle_check_signal(
    strategy: IStrategyPort,
    trend_data: IndicatorData | None,
    signal_data: IndicatorData | None,
    symbol: str,
    log: Logger,
) -> CheckSignalEvent:
    """Consulta a estratégia para sinal de entrada no último candle."""
    if trend_data is None or signal_data is None:
        return CheckSignalEvent.NO_DATA

    signal = strategy.check_signal(trend_data, signal_data)

    if signal == "buy":
        log.info(f"[{symbol}] Sinal de COMPRA.")
        return CheckSignalEvent.BUY
    if signal == "sell":
        log.info(f"[{symbol}] Sinal de VENDA.")
        return CheckSignalEvent.SELL

    log.info(f"[{symbol}] Sem sinal. Aguardando próximo candle.")
    return CheckSignalEvent.NO_SIGNAL
