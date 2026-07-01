from typing import Optional


def ema(data: list[float], period: int = 9) -> list[Optional[float]]:
    """
    Calcula a Média Móvel Exponencial (EMA) de uma lista de floats.

    Args:
        data: lista de valores (ex: preços de fechamento)
        period: período de cálculo da EMA (padrão: 9)

    Returns:
        Lista de floats com os valores da EMA. Os primeiros (period - 1)
        valores ficam vazios (None), pois não há dados suficientes ainda.
    """
    if period <= 0:
        raise ValueError("O período deve ser maior que zero.")
    if len(data) < period:
        raise ValueError("A quantidade de dados é menor que o período informado.")

    k = 2 / (period + 1)  # fator de suavização
    ema_values: list[Optional[float]] = [None] * (period - 1)

    # Primeiro valor da EMA = média simples (SMA) dos primeiros 'period' valores
    sma = sum(data[:period]) / period
    ema_values.append(sma)

    # Cálculo recursivo da EMA para os valores seguintes
    for price in data[period:]:
        prev_ema = ema_values[-1]
        if prev_ema is None:
            raise RuntimeError("Previous EMA value is missing.")
        current_ema = (price - prev_ema) * k + prev_ema
        ema_values.append(current_ema)

    return ema_values
