import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FetchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fetch_retry_attempts: int = Field(gt=0)
    fetch_retry_delay: int = Field(gt=0)
    batch_limit: int = Field(gt=0)
    max_rows: int = Field(gt=0)


class MonitoringConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_monitoring_failures: int = Field(gt=0)
    monitoring_heartbeat_every: int = Field(gt=0)
    monitoring_check_interval_seconds: int = Field(gt=0)
    error_wait_seconds: int = Field(gt=0)
    cleanup_max_retries: int = Field(gt=0)
    error_max_retries: int = Field(gt=0)


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sl_confirm_attempts: int = Field(gt=0)
    sl_confirm_delay_seconds: float = Field(gt=0)
    fetch_positions_timeout_seconds: float = Field(gt=0)
    normalize_max_attempts: int = Field(gt=0)
    normalize_retry_delay_seconds: float = Field(gt=0)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    log_max_bytes: int = Field(ge=3145728)  # min 3 MB
    log_backup_count: int = Field(gt=0)


class MarketHoursConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_open_day: int = Field(ge=0, le=6)    # 0=Segunda … 6=Domingo
    market_open_hour: int = Field(ge=0, le=23)
    market_open_minute: int = Field(ge=0, le=59)
    market_close_day: int = Field(ge=0, le=6)
    market_close_hour: int = Field(ge=0, le=23)
    market_close_minute: int = Field(ge=0, le=59)


class SystemSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str = "America/Sao_Paulo"
    fetch: FetchConfig
    monitoring: MonitoringConfig
    execution: ExecutionConfig
    logging: LoggingConfig
    market_hours: MarketHoursConfig

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
            return v
        except ZoneInfoNotFoundError as e:
            raise ValueError(
                f"Timezone inválido: '{v}'. Exemplo válido: 'America/Sao_Paulo'"
            ) from e


def load_system_settings(filepath: str) -> SystemSettings:
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"Arquivo '{path.name}' não encontrado em '{path.parent}'")

    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Erro de sintaxe no arquivo '{path.name}', {e}") from e

    if not data:
        raise ValueError(f"Arquivo '{path.name}' vazio")

    return SystemSettings(**data)
