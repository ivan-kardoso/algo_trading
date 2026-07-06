"""Handlers de estratégia: APPLY_STRATEGY, CHECK_SIGNAL."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast


from ...domain.ports import IMarketDataRepository, IStrategyPort, OHLCVData
from ...domain.state_machine.transitions import (
    ApplyStrategyEvent,
    CheckSignalEvent,
)

if TYPE_CHECKING:
    from loguru import Logger


def handle_apply_strategy(
    strategy: IStrategyPort,
    repo: IMarketDataRepository,
    symbol: str,
    log: Logger,
) -> tuple[ApplyStrategyEvent, OHLCVData | None]:
    """Aplica indicadores ao dataset atual.

    Retorna (event, dataset_processado). O dataset processado é passado
    adiante ao handle_check_signal pelo runner; nunca persiste em disco.
    """
    data = repo.get_dataset()
    if not data:
        log.info(f"[{symbol}] Dataset vazio. Aguardando próximo candle.")
        return ApplyStrategyEvent.EMPTY, None

    processed = strategy.apply_indicators(data)
    log.info(f"[{symbol}] Indicadores calculados.")
    return ApplyStrategyEvent.HAS_DATA, processed


def handle_check_signal(
    strategy: IStrategyPort,
    data: OHLCVData | None,
    symbol: str,
    log: Logger,
) -> CheckSignalEvent:
    """Consulta a estratégia para sinal de entrada no último candle."""
    if data is None:
        return CheckSignalEvent.NO_DATA

    # strategy.check_signal expects an IndicatorData-like object; at runtime
    # the repo provides OHLCVData which is acceptable. Cast to Any to satisfy
    # static type checkers.
    signal = strategy.check_signal(cast(Any, data))

    if signal == "buy":
        log.info(f"[{symbol}] Sinal de COMPRA.")
        return CheckSignalEvent.BUY
    if signal == "sell":
        log.info(f"[{symbol}] Sinal de VENDA.")
        return CheckSignalEvent.SELL

    log.info(f"[{symbol}] Sem sinal. Aguardando próximo candle.")
    return CheckSignalEvent.NO_SIGNAL


# HANDLE DE TESTE
# def handle_check_signal(
#     strategy: IStrategyPort,
#     data: IndicatorData | None,
#     symbol: str,
#     log: Logger,
# ) -> CheckSignalEvent:
#     """TESTE: apenas checagem de alinhamento das EMAs (sem sinal de entrada)."""
#     if data is None:
#         return CheckSignalEvent.NO_DATA

#     i = len(data.candles) - 1
#     f = data.ema_fast[i]
#     m = data.ema_medium[i]
#     s = data.ema_slow[i]

#     if f is None or m is None or s is None:
#         return CheckSignalEvent.NO_SIGNAL

#     strategy._check_alignment(f, m, s)  # type: ignore[attr-defined]
#     return CheckSignalEvent.NO_SIGNAL
