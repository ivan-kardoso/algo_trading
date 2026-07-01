from pathlib import Path
import tomllib

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ..domain.models.strategy_names import VALID_STRATEGIES
from ..domain.models.ohlcv_field import VALID_OHLCV_FIELDS


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


def load_strategy_settings(filepath: str) -> StrategySettings:
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo '{path.name}' não encontrado em: '{path.parent}'"
        )

    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Erro de sintaxe no arquivo '{path.name}', {e}") from e

    if not data:
        raise ValueError(f"Arquivo '{path.name}' vazio.")

    return StrategySettings(**data)
