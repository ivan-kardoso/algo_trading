from typing import Optional
from ..domain.models.indicator_data import MACDResult
from .ema import ema


def macd(
    close: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDResult:

    if fast_period >= slow_period:
        raise ValueError("fast_period deve ser menor que slow_period.")

    ema_fast = ema(close, fast_period)
    ema_slow = ema(close, slow_period)

    # Linha MACD
    macd_line: list[Optional[float]] = []

    for fast, slow in zip(ema_fast, ema_slow):
        if fast is None or slow is None:
            macd_line.append(None)
        else:
            macd_line.append(fast - slow)

    # Remove os None para calcular a Signal
    macd_valid = [v for v in macd_line if v is not None]

    signal_valid = ema(macd_valid, signal_period)

    # Alinha a Signal com o tamanho da linha MACD
    signal_line: list[Optional[float]] = [None] * len(macd_line)

    idx = 0
    for i, value in enumerate(macd_line):
        if value is not None:
            signal_line[i] = signal_valid[idx]
            idx += 1

    # Histograma
    histogram: list[Optional[float]] = []

    for macd_value, signal_value in zip(macd_line, signal_line):
        if macd_value is None or signal_value is None:
            histogram.append(None)
        else:
            histogram.append(macd_value - signal_value)

    return MACDResult(macd=macd_line, signal=signal_line, histogram=histogram)
