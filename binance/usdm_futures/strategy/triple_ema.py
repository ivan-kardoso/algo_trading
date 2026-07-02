"""Estratégia Triple EMA — implementação de IStrategyPort."""

from __future__ import annotations

from typing import Literal

from ..domain.models.indicator_data import IndicatorData

from ..config.strategy_config import StrategySettings
from ..domain.ports import IStrategyPort, OHLCVData
from ..indicators import ema

_FIELD_INDEX: dict[str, int] = {
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
}


class TripleEmaStrategy(IStrategyPort):
    def __init__(self, settings: StrategySettings) -> None:
        self._settings = settings
        self._field_index = _FIELD_INDEX[settings.field]

    def apply_indicators(self, data: OHLCVData) -> IndicatorData:
        series = [row[self._field_index] for row in data]
        return IndicatorData(
            candles=data,
            ema_fast=ema(series, self._settings.fast_period),
            ema_medium=ema(series, self._settings.medium_period),
            ema_slow=ema(series, self._settings.slow_period),
        )

    def _compute_emas(self, data: OHLCVData):
        series = [row[self._field_index] for row in data]
        fast = ema(series, self._settings.fast_period)
        medium = ema(series, self._settings.medium_period)
        slow = ema(series, self._settings.slow_period)
        return fast, medium, slow

    def check_signal(self, data: OHLCVData) -> Literal["buy", "sell"] | None:
        fast, medium, slow = self._compute_emas(data)
        px = self._field_index

        armed: Literal["buy", "sell"] | None = None  # gatilho armado e seu lado

        # Varre o dataset inteiro reconstruindo o estado do gatilho candle a candle.
        # Começa em 1 (precisa do candle anterior); ignora candles sem as 3 EMAs.
        for i in range(1, len(data)):
            fast_value = fast[i]
            medium_value = medium[i]
            slow_value = slow[i]

            if fast_value is None or medium_value is None or slow_value is None:
                continue

            close = data[i][px]
            prev_close = data[i - 1][px]
            f, m, s = fast_value, medium_value, slow_value

            up = f > m > s  # alinhamento de alta
            down = f < m < s  # alinhamento de baixa

            # 1) Desarme (precede tudo): gatilho de compra morre ao fechar < slow;
            #    o de venda morre ao fechar > slow.
            if armed == "buy" and close < s:
                armed = None
            elif armed == "sell" and close > s:
                armed = None

            # 2) Disparo: com gatilho armado, fechar acima/abaixo da rápida gera sinal.
            if armed == "buy" and close > f:
                # sinal só vale se for o último candle (o candle "atual")
                if i == len(data) - 1:
                    return "buy"
                armed = None  # disparou no passado; consome o gatilho
                continue
            if armed == "sell" and close < f:
                if i == len(data) - 1:
                    return "sell"
                armed = None
                continue

            # 3) Armação: veio de cima (prev acima da rápida) + pullback (close <= rápida
            #    ou <= média), dentro de alinhamento de alta → arma compra. Espelhado p/ venda.
            if armed is None:
                if up and prev_close > f and (close <= f or close <= m):
                    armed = "buy"
                elif down and prev_close < f and (close >= f or close >= m):
                    armed = "sell"

        return None
