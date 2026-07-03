"""Estratégia Triple EMA — implementação de IStrategyPort."""

from __future__ import annotations

from typing import Literal

from ..config.strategy_config import StrategySettings
from ..domain.models.indicator_data import IndicatorData
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

        # Estado do gatilho (memória entre candles).
        self._armed: Literal["buy", "sell"] | None = None
        # Timestamp do último candle já processado (garante avanço na série).
        self._last_ts: float | None = None

    def apply_indicators(self, data: OHLCVData) -> IndicatorData:
        series = [row[self._field_index] for row in data]
        return IndicatorData(
            candles=data,
            ema_fast=ema(series, self._settings.fast_period),
            ema_medium=ema(series, self._settings.medium_period),
            ema_slow=ema(series, self._settings.slow_period),
        )

    def check_signal(self, data: IndicatorData) -> Literal["buy", "sell"] | None:
        candles = data.candles
        if len(candles) < 2:
            return None

        px = self._field_index
        i = len(candles) - 1  # candle atual (o que acabou de fechar)

        # Validação #1: a série precisa avançar. Só processa se o timestamp
        # do candle atual for maior que o do último candle já processado.
        current_ts = candles[i][0]
        if self._last_ts is not None and current_ts <= self._last_ts:
            return None
        self._last_ts = current_ts

        f = data.ema_fast[i]
        m = data.ema_medium[i]
        s = data.ema_slow[i]
        # EMAs ainda não aquecidas: sem base para avaliar.
        if f is None or m is None or s is None:
            return None

        close = candles[i][px]
        prev_open = candles[i - 1][1]
        prev_close = candles[i - 1][px]
        prev_f = data.ema_fast[i - 1]

        up = f > m > s  # alinhamento de alta
        down = f < m < s  # alinhamento de baixa

        # 1) Desarme (precede tudo): fechar contra a lenta zera o gatilho.
        if self._armed == "buy" and close < s:
            self._armed = None
        elif self._armed == "sell" and close > s:
            self._armed = None

        # 2) Disparo: com gatilho armado, o primeiro candle que fecha acima
        #    (compra) / abaixo (venda) da rápida é o sinal. Consome o gatilho.
        if self._armed == "buy" and close > f:
            self._armed = None
            return "buy"
        if self._armed == "sell" and close < f:
            self._armed = None
            return "sell"

        # 3) Armação: veio de cima (prev acima da rápida) + pullback
        #    (close <= rápida ou <= média), em alinhamento de alta → arma compra.
        #    Espelhado para venda.
        if self._armed is None and prev_f is not None:
            prev_above = prev_open > prev_f and prev_close > prev_f
            prev_below = prev_open < prev_f and prev_close < prev_f
            if up and prev_above and (close <= f or close <= m):
                self._armed = "buy"
            elif down and prev_below and (close >= f or close >= m):
                self._armed = "sell"

        return None
