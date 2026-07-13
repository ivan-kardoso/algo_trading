"""Estratégia Triple EMA — implementação de IStrategyPort.

Multi-timeframe: recebe de 1 a 4 datasets mapeados por papel
(signal/trend/aux_1/aux_2, apenas os preenchidos no TOML).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from ..config.strategy_config import StrategySettings
from ..indicators import ema
from ..domain.models.indicator_data import IndicatorData
from ..domain.ports import OHLCVData
from ..domain.ports.strategy import IStrategyPort

if TYPE_CHECKING:
    from loguru import Logger

_FIELD_INDEX: dict[str, int] = {
    "open": 1,
    "high": 2,
    "low": 3,
    "close": 4,
    "volume": 5,
}


class TripleEmaStrategy(IStrategyPort):
    def __init__(
        self,
        settings: StrategySettings,
        timeframes: dict[str, str],
        log: Logger,
    ) -> None:
        self._settings = settings
        self._timeframes = timeframes
        self._log = log
        self._field_index = _FIELD_INDEX[settings.field]
        self._trend_lock_pending: bool = True
        self._trend_blocked: Literal["buy", "sell"] | None = None
        self._trend_released: bool = False

    # Método do contrato IStrategyPort, chamado pelo handler (não por esta classe).
    # Nome genérico de propósito: a interface serve a qualquer estratégia;
    # aqui a implementação calcula 3 EMAs, mas o contrato não se amarra a isso.
    def apply_indicators(self, datasets: dict[str, OHLCVData]) -> dict[str, IndicatorData]:
        result: dict[str, IndicatorData] = {}
        for role, data in datasets.items():
            series = [row[self._field_index] for row in data]
            result[role] = IndicatorData(
                candles=data,
                ema_fast=ema(series, self._settings.fast_period),
                ema_medium=ema(series, self._settings.medium_period),
                ema_slow=ema(series, self._settings.slow_period),
            )
        return result

    def _check_alignment(self, f: float, m: float, s: float) -> Literal["buy", "sell"] | None:
        return "buy" if f > m > s else "sell" if f < m < s else None

    def _is_trend_released(self, trend_side: Literal["buy", "sell"] | None) -> bool:
        if self._trend_released:
            return True

        if self._trend_lock_pending:
            self._trend_blocked = trend_side
            self._trend_lock_pending = False
            if trend_side is not None:
                self._log.log(
                    "LOCK",
                    f"Alihamento inicial {'compra.' if self._trend_blocked == 'buy' else 'venda.' if self._trend_blocked == 'sell' else 'indefinido.'} Aguardando reversão.",
                )

        if trend_side != self._trend_blocked:
            self._trend_released = True
            self._log.log("UNLOCK", "Trava liberada — operação habilitada.")
            return True

        return False

    def _is_trend_aligned(self, indicators: dict[str, IndicatorData]) -> Literal["buy", "sell"] | None:
        trend = indicators.get("trend")
        if trend is None:
            return None

        i = len(trend.candles) - 1
        if i < 0:
            return None

        f = trend.ema_fast[i]
        m = trend.ema_medium[i]
        s = trend.ema_slow[i]
        if f is None or m is None or s is None:
            return None

        timeframe = self._timeframes.get("trend", "trend")
        alignment = self._check_alignment(f, m, s)

        if alignment == "buy":
            self._log.log("TREND", f"timeframe {timeframe} Alinhamento EMA para compra.")
        elif alignment == "sell":
            self._log.log("TREND", f"timeframe {timeframe} Alinhamento EMA para venda.")
        else:
            self._log.log("TREND", f"timeframe {timeframe} EMA sem alinhamento.")

        return alignment

    def _is_signal_aligned(self, indicators: dict[str, IndicatorData]) -> Literal["buy", "sell"] | None:
        signal = indicators.get("signal")
        if signal is None:
            return None

        i = len(signal.candles) - 1
        if i < 0:
            return None

        f = signal.ema_fast[i]
        m = signal.ema_medium[i]
        s = signal.ema_slow[i]
        if f is None or m is None or s is None:
            return None

        timeframe = self._timeframes.get("signal", "signal")
        alignment = self._check_alignment(f, m, s)

        if alignment == "buy":
            self._log.log("TREND", f"timeframe {timeframe} Alinhamento EMA para compra.")
        elif alignment == "sell":
            self._log.log("TREND", f"timeframe {timeframe} Alinhamento EMA para venda.")
        else:
            self._log.log("TREND", f"timeframe {timeframe} Alinhamento indefinido.")

        return alignment

    def _check_buy_trigger(self, data: IndicatorData) -> bool:
        candles = data.candles
        i = len(candles) - 1
        if i < 1:
            return False

        f = data.ema_fast[i]
        s = data.ema_slow[i]
        if f is None or s is None:
            return False

        open_ = candles[i][1]
        close = candles[i][4]

        # Pullback: fecha abaixo da rápida, mas abre acima da lenta.
        if not (close < f and open_ > s):
            return False

        timeframe = self._timeframes.get("signal", "signal")

        # (1) Veio de cima pelo próprio candle.
        if open_ > f:
            self._log.log("TREND", f"timeframe {timeframe} Gatilho de compra armado.")
            return True

        # (2) Senão, olha o candle anterior.
        prev_f = data.ema_fast[i - 1]
        prev_open = candles[i - 1][1]
        if prev_f is not None and prev_open > prev_f:
            self._log.log("TREND", f"timeframe {timeframe} Gatilho de compra armado.")
            return True

        return False

    def check_signal(self, indicators: dict[str, IndicatorData]) -> Literal["buy", "sell"] | None:
        trend_side = self._is_trend_aligned(indicators)

        if not self._is_trend_released(trend_side):
            return None

        if trend_side is None:
            return None

        signal_side = self._is_signal_aligned(indicators)
        if signal_side != trend_side:
            return None

        # Cenário alinhado: trend e signal no mesmo lado (trend_side).
        # Gatilho e sinal de entrada vêm aqui depois.

        return None
