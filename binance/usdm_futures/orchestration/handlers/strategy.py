"""Handlers de estratégia: APPLY_STRATEGY, CHECK_SIGNAL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from ...domain.models.indicator_data import IndicatorData
from ...domain.models.timeframe_slot import TimeframeSlot
from ...domain.ports import IMarketDataRepository, IStrategyPort
from ...domain.state_machine.transitions import (
    ApplyStrategyEvent,
    CheckSignalEvent,
)

if TYPE_CHECKING:
    from loguru import Logger


def handle_apply_strategy(
    strategy: IStrategyPort,
    repos: Mapping[TimeframeSlot, IMarketDataRepository],
    symbol: str,
    log: Logger,
) -> tuple[ApplyStrategyEvent, dict[TimeframeSlot, IndicatorData] | None]:
    """Aplica indicadores aos datasets dos timeframes preenchidos.

    Retorna (event, indicadores_processados). Os indicadores processados
    são passados adiante ao handle_check_signal pelo runner; nunca
    persistem em disco. Mapeados por posição (timeframe_1..timeframe_4),
    contendo apenas os timeframes efetivamente preenchidos.
    """
    datasets = {slot: repo.get_dataset() for slot, repo in repos.items()}
    if any(not data for data in datasets.values()):
        log.info(f"[{symbol}] Dataset vazio. Aguardando próximo candle.")
        return ApplyStrategyEvent.EMPTY, None

    processed = strategy.apply_indicators(datasets)
    log.info(f"[{symbol}] Indicadores calculados.")
    return ApplyStrategyEvent.HAS_DATA, processed


def handle_check_signal(
    strategy: IStrategyPort,
    processed: dict[TimeframeSlot, IndicatorData] | None,
    symbol: str,
    log: Logger,
) -> CheckSignalEvent:
    """Consulta a estratégia para sinal de entrada no último candle."""
    if processed is None:
        return CheckSignalEvent.NO_DATA

    signal = strategy.check_signal(processed)

    if signal == "buy":
        log.info(f"[{symbol}] Sinal de COMPRA.")
        return CheckSignalEvent.BUY
    if signal == "sell":
        log.info(f"[{symbol}] Sinal de VENDA.")
        return CheckSignalEvent.SELL

    log.info(f"[{symbol}] Sem sinal. Aguardando próximo candle.")
    return CheckSignalEvent.NO_SIGNAL
