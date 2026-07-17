from pathlib import Path
import tomllib

from pydantic import BaseModel, ConfigDict, Field, field_validator
from ..domain.models.strategy_names import VALID_STRATEGIES
from ..domain.models.ohlcv_field import VALID_OHLCV_FIELDS
from ..domain.models.timeframe_slot import TimeframeSlot

_VALID_SLOTS = {slot.value for slot in TimeframeSlot}


class StrategySettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    field: str

    fast_period: int = Field(gt=0)
    medium_period: int = Field(gt=0)
    slow_period: int = Field(gt=0)

    # Mapeamento papel da estratégia -> posição de timeframe do símbolo.
    # "signal" e "trend" são obrigatórios para a triple-ema; aux_1/aux_2 são
    # opcionais, presentes apenas se a estratégia os utilizar.
    signal: str | None = None
    trend: str | None = None
    aux_1: str | None = None
    aux_2: str | None = None

    # Posição de timeframe que dita o ritmo do loop. Independente do signal.
    ritmo: str

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

    @field_validator("signal", "trend", "aux_1", "aux_2")
    @classmethod
    def validate_role_position(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        if v not in _VALID_SLOTS:
            raise ValueError(
                f"Posição inválida: '{v}'. Valores aceitos: {sorted(_VALID_SLOTS)}"
            )
        return v

    @field_validator("ritmo")
    @classmethod
    def validate_ritmo(cls, v: str) -> str:
        if v not in _VALID_SLOTS:
            raise ValueError(
                f"Ritmo inválido: '{v}'. Valores aceitos: {sorted(_VALID_SLOTS)}"
            )
        return v

    def role_positions(self) -> dict[str, str]:
        """Mapeamento papel -> posição, apenas para os papéis preenchidos."""
        roles = {"signal": self.signal, "trend": self.trend, "aux_1": self.aux_1, "aux_2": self.aux_2}
        return {role: position for role, position in roles.items() if position is not None}


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
