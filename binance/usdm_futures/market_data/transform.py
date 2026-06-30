from ..domain.ports import OHLCVData


class OHLCVTransform:
    def validate(self, candles: OHLCVData, timeframe_ms: int) -> None:
        """Verifica que não há gaps de timestamp entre candles consecutivos.

        O último candle é ignorado pois pode estar incompleto (ainda aberto
        na exchange no momento do download).
        """
        if len(candles) <= 2:
            return

        for i in range(1, len(candles) - 1):
            diff = int(candles[i][0]) - int(candles[i - 1][0])
            if diff != timeframe_ms:
                raise ValueError(
                    f"Gap detectado: {candles[i - 1][0]} → {candles[i][0]} "
                    f"(diferença: {diff}ms, esperado: {timeframe_ms}ms)"
                )
