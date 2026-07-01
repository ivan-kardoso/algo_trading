import tomllib
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..domain.models.strategy_names import VALID_STRATEGIES
from ..domain.models.timeframes import VALID_TIMEFRAMES
from ..domain.models.ohlcv_field import VALID_OHLCV_FIELDS


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timeframe: str
    since: str | None = None
    candle_limit: int | None = None

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        if v not in VALID_TIMEFRAMES:
            raise ValueError(
                f"Timeframe inválido: '{v}'. Valores aceitos: {sorted(VALID_TIMEFRAMES)}"
            )
        return v

    @field_validator("since")
    @classmethod
    def validate_since_format(cls, v: str) -> str:
        if not v:
            return v
        try:
            datetime.strptime(v, "%d/%m/%Y")
            return v
        except Exception as e:
            raise ValueError(
                f"Since não possui o formato correto '{v}'. Deve ser (dia/mês/ano)."
            ) from e

    @model_validator(mode="after")
    def validate_since_and_candle_limit(self) -> Self:
        if not self.since and not self.candle_limit:
            raise ValueError(
                f"Since: {self.since} e Candle Limit: {self.candle_limit} estão vazios.\n"
                f"Ao menos um dos dois deve ter um valor válido."
            )
        return self


class OrderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(gt=0)
    order_type: Literal["market", "limit"]
    chase_percent: float = Field(gt=0)
    offset_percent: float = Field(gt=0)
    fill_timeout: int = Field(gt=0)
    max_retries: int = Field(gt=0)


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stop_loss_percent: float = Field(gt=0)
    take_profit_percent: float = Field(gt=0)
    leverage: int = Field(gt=0)


class StrategySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    field: str

    fast_period: int = Field(gt=0)
    medium_period: int = Field(gt=0)
    slow_period: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in VALID_STRATEGIES:
            raise ValueError(
                f"Estratégia inválida: '{v}'. Estratégias válidas: {sorted(VALID_STRATEGIES)}"
            )
        return v

    @field_validator("field")
    @classmethod
    def validate_ohlcv_field(cls, v: str) -> str:
        if v not in VALID_OHLCV_FIELDS:
            raise ValueError(
                f"Campo inválido: '{v}'. Field válido para cálculo: 'open', 'high', 'low', 'close', 'volume'"
            )
        return v


class AssetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: ClassVar[str] = "binance"
    market_type: ClassVar[str] = "future"

    symbol: str
    strategy: str
    sandbox: bool = True
    data: DataConfig
    orders: OrderConfig
    risk: RiskConfig
    strategy_settings: StrategySettings

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        if "/" not in v or ":" not in v:
            raise ValueError(
                f"'symbol' deve estar no formato unificado do ccxt (ex: 'BTC/USDT:USDT'), recebido: '{v}'"
            )
        return v

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        if v not in VALID_STRATEGIES:
            raise ValueError(
                f"Estratégia inválida: '{v}'. Estratégias válidas: {sorted(VALID_STRATEGIES)}"
            )
        return v


def load_asset_settings(filepath: str) -> AssetSettings:
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo '{path.name}' não encontrado em '{path.parent}'"
        )

    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Erro de sintaxe no arquivo '{path.name}', {e}") from e

    if not data:
        raise ValueError(f"Arquivo '{path.name}' vazio.")

    return AssetSettings(**data)
