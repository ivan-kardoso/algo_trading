"""Estratégia Triple EMA — implementação de IStrategyPort."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from loguru import Logger

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
    def __init__(self, settings: StrategySettings, log: Logger) -> None:
        self._settings = settings
        self._field_index = _FIELD_INDEX[settings.field]
        self._log = log
        self._last_alignment: Literal["buy", "sell", "init"] | None = "init"

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

    def _check_alignment(
        self, f: float, m: float, s: float
    ) -> Literal["buy", "sell"] | None:
        if f > m > s:
            alignment = "buy"
        elif f < m < s:
            alignment = "sell"
        else:
            alignment = None

        if alignment != self._last_alignment:
            if alignment == "buy":
                self._log.info("Triple EMA alinhada para compra")
            elif alignment == "sell":
                self._log.info("Triple EMA alinhada para venda")
            else:
                self._log.info("Triple EMA sem alinhamento")
            self._last_alignment = alignment

        return alignment

    def _check_buy_trigger(self, data: IndicatorData, i: int) -> bool:
        candles = data.candles
        px = self._field_index

        f = data.ema_fast[i]
        s = data.ema_slow[i]
        if f is None or s is None:
            return False

        close = candles[i][px]
        open_ = candles[i][1]

        # Pullback: fechamento estritamente entre a lenta e a rápida.
        if not (s < close <= f):
            return False

        # (1) Abertura do candle atual acima da rápida dele mesmo.
        if open_ > f:
            self._log.info("Gatilho de compra armado")
            return True

        # (2) Senão, olha o candle anterior.
        if i - 1 < 0:
            return False
        prev_f = data.ema_fast[i - 1]
        prev_open = candles[i - 1][1]
        if prev_f is None:
            return False
        if prev_open > prev_f:
            self._log.info("Gatilho de compra armado")
            return True
        return False

    def _check_sell_trigger(self, data: IndicatorData, i: int) -> bool:
        candles = data.candles
        px = self._field_index

        f = data.ema_fast[i]
        s = data.ema_slow[i]
        if f is None or s is None:
            return False

        close = candles[i][px]
        open_ = candles[i][1]

        # Pullback: fechamento estritamente entre a rápida e a lenta.
        if not (f <= close < s):
            return False

        # (1) Abertura do candle atual abaixo da rápida dele mesmo.
        if open_ < f:
            self._log.info("Gatilho de venda armado")
            return True

        # (2) Senão, olha o candle anterior.
        if i - 1 < 0:
            return False
        prev_f = data.ema_fast[i - 1]
        prev_open = candles[i - 1][1]
        if prev_f is None:
            return False
        if prev_open < prev_f:
            self._log.info("Gatilho de venda armado")
            return True
        return False

    def _check_armed_signal(
        self, data: IndicatorData, i: int, alignment: Literal["buy", "sell"] | None
    ) -> Literal["buy", "sell"] | None:
        candles = data.candles
        px = self._field_index
        f = data.ema_fast[i]
        s = data.ema_slow[i]
        if f is None or s is None:
            return None

        close = candles[i][px]
        side = self._armed

        if side == "buy":
            # 1) alinhamento perdido
            if alignment != "buy":
                self._log.info("Gatilho de compra desarmado: alinhamento perdido")
                self._armed = None
                return None
            # 2) fechou abaixo da lenta
            if close < s:
                self._log.info(
                    "Gatilho de compra desarmado: fechou abaixo da média lenta"
                )
                self._armed = None
                return None
            # 3) fechou acima da rápida -> dispara
            if close > f:
                self._log.info("Sinal de COMPRA detectado")
                self._armed = None
                return "buy"
            # 4) segue armado
            return None

        if side == "sell":
            if alignment != "sell":
                self._log.info("Gatilho de venda desarmado: alinhamento perdido")
                self._armed = None
                return None
            if close > s:
                self._log.info("Gatilho de venda desarmado: fechou acima da média lenta")
                self._armed = None
                return None
            if close < f:
                self._log.info("Sinal de VENDA detectado")
                self._armed = None
                return "sell"
            return None

        return None

    def check_signal(self, data: IndicatorData) -> Literal["buy", "sell"] | None:
        candles = data.candles
        if not candles:
            return None

        i = len(candles) - 1
        f = data.ema_fast[i]
        m = data.ema_medium[i]
        s = data.ema_slow[i]
        if f is None or m is None or s is None:
            return None

        alignment = self._check_alignment(f, m, s)

        if alignment == "buy":
            self._check_buy_trigger(data, i)
        elif alignment == "sell":
            self._check_sell_trigger(data, i)

        return None
