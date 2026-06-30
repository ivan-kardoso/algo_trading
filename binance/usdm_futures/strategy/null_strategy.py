"""Implementação-placeholder de IStrategyPort — sem lógica de sinal."""

from __future__ import annotations

from typing import Literal

from ..domain.ports import IStrategyPort, OHLCVData


class NullStrategy(IStrategyPort):
    """Estratégia nula: não aplica indicadores, nunca emite sinal.

    PENDÊNCIA: substituir por implementação real em conversa futura.
    Mantém o robô em CHECK_SIGNAL → STANDBY indefinidamente.
    """

    def apply_indicators(self, data: OHLCVData) -> OHLCVData:
        return data

    def check_signal(self, data: OHLCVData) -> Literal["buy", "sell"] | None:
        return None
