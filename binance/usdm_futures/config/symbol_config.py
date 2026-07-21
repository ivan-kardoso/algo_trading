import tomllib
from pathlib import Path
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..domain.models.strategy_names import VALID_STRATEGIES


class OrderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    margin_usdt: float = Field(gt=0)
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


class AssetSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exchange: ClassVar[str] = "binance"
    market_type: ClassVar[str] = "future"

    symbol: str
    strategy: str
    sandbox: bool = True
    orders: OrderConfig
    risk: RiskConfig

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
