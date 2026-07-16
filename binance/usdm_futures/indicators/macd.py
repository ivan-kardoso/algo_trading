from typing import Optional
from ..domain.models.indicator_data import MACDResult
from .ema import ema


def macd(
    data: list[float],
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> MACDResult:
    """Calcula o MACD (Moving Average Convergence Divergence).

    Calcula a linha MACD subtraindo a EMA de período lento da EMA de período
    rápido, a linha Signal como a EMA da linha MACD e o Histograma como a
    diferença entre MACD e Signal. Valores iniciais insuficientes são alinhados
    como `None` para preservar o tamanho da série de entrada.

    Args:
        data: Lista de valores numéricos (por exemplo, preços de fechamento).
        fast_period: Período da EMA rápida (padrão: 12). Deve ser menor que
            `slow_period`.
        slow_period: Período da EMA lenta (padrão: 26). Deve ser maior que
            `fast_period`.
        signal_period: Período da EMA usada para calcular a linha Signal
            (padrão: 9).

    Returns:
        MACDResult: Objeto contendo três listas (`macd`, `signal`, `histogram`),
        cada uma com o mesmo comprimento de `data`. Entradas iniciais que não
        podem ser calculadas estão representadas por `None`.

    Raises:
        ValueError: Se `fast_period` for maior ou igual a `slow_period`.
        ValueError: Se a quantidade de elementos em `data` for menor que
            `slow_period`.

    Example:
        >>> from binance.usdm_futures.indicators.macd import macd
        >>> result = macd([1.0, 1.1, 1.2, ...])
        >>> len(result.macd) == len(result.signal) == len(result.histogram)
        True
    """

    if fast_period >= slow_period:
        raise ValueError("fast_period deve ser menor que slow_period.")

    if len(data) < slow_period:
        raise ValueError(f"A quantidade da dados é insuficiente. Dados: {len(data)}, Período: {slow_period}")

    ema_fast = ema(data, fast_period)
    ema_slow = ema(data, slow_period)

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
