from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..config.schedule import SystemSettings


class MarketHoursChecker:
    """Verifica se o horário atual está dentro da janela operacional configurada."""

    def __init__(self, settings: SystemSettings) -> None:
        self._tz = ZoneInfo(settings.timezone)
        mh = settings.market_hours
        self._open_day = mh.market_open_day
        self._open_hour = mh.market_open_hour
        self._open_minute = mh.market_open_minute
        self._close_day = mh.market_close_day
        self._close_hour = mh.market_close_hour
        self._close_minute = mh.market_close_minute

    def is_market_open(self) -> bool:
        """Retorna True se o horário atual está dentro da janela operacional.

        Compara a ocorrência mais recente de abertura e de fechamento:
        se a abertura mais recente é posterior ao fechamento mais recente,
        estamos dentro da janela.
        """
        now = datetime.now(self._tz)
        prev_open = self._previous_occurrence(
            now, self._open_day, self._open_hour, self._open_minute
        )
        prev_close = self._previous_occurrence(
            now, self._close_day, self._close_hour, self._close_minute
        )
        return prev_open > prev_close

    def seconds_until_next_open(self) -> int:
        """Segundos até a próxima abertura. Retorna 0 se já está aberto.

        Usa math.ceil para evitar truncar fração de segundo para 0
        e entrar em busy-wait no STANDBY.
        """
        if self.is_market_open():
            return 0
        now = datetime.now(self._tz)
        next_open = self._next_occurrence(
            now, self._open_day, self._open_hour, self._open_minute
        )
        delta = (next_open - now).total_seconds()
        return max(1, math.ceil(delta))

    @staticmethod
    def _previous_occurrence(
        now: datetime, day: int, hour: int, minute: int
    ) -> datetime:
        """Ocorrência mais recente (<= now) de um (weekday, hour, minute)."""
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_back = (now.weekday() - day) % 7
        candidate = target - timedelta(days=days_back)
        if candidate > now:
            candidate -= timedelta(days=7)
        return candidate

    @staticmethod
    def _next_occurrence(
        now: datetime, day: int, hour: int, minute: int
    ) -> datetime:
        """Próxima ocorrência (> now) de um (weekday, hour, minute)."""
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        days_fwd = (day - now.weekday()) % 7
        candidate = target + timedelta(days=days_fwd)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate
