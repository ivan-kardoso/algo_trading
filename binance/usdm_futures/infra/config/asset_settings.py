"""Configurações de símbolos (pares de trading) do bot Binance USDM Futures.

Este módulo fornece classes para validar e carregar configurações de pares
de trading (ex: BTC/USDT:USDT) a partir de arquivos TOML. Inclui validação
de dados operacionais (candles, ordens, risco) via Pydantic.
"""

import tomllib
from pathlib import Path
from datetime import datetime
from typing import ClassVar, Literal, Self

from ...domain.models.strategy_names import VALID_STRATEGIES
from ...domain.models.timeframes import VALID_TIMEFRAMES
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataConfig(BaseModel):
    """Configurações de dados históricos (candles) para um par de trading.

    Attributes:
        timeframe: Intervalo de tempo dos candles (ex.: "1h", "4h", "1d").
        since: Data inicial de busca no formato "dia/mês/ano" (ex.: "01/01/2024"). Opcional.
        candle_limit: Quantidade máxima de candles a buscar. Opcional.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    timeframe: str
    since: str | None = None
    candle_limit: int | None = None

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        """Valida se o timeframe informado está entre os valores aceitos.

        Args:
            v: Timeframe a ser validado (ex.: "1h", "4h").

        Returns:
            O mesmo valor `v`, caso seja um timeframe válido.

        Raises:
            ValueError: Se `v` não estiver na lista de timeframes aceitos.
        """
        if v not in VALID_TIMEFRAMES:
            raise ValueError(
                f"Timeframe inválido: '{v}'. Valores aceitos: {sorted(VALID_TIMEFRAMES)}"
            )

        return v

    @field_validator("since")
    @classmethod
    def validate_since_format(cls, v: str) -> str:
        """Valida se o campo `since` está no formato "dia/mês/ano".

        Args:
            v: String de data a ser validada.

        Returns:
            O mesmo valor `v`, caso esteja no formato correto.

        Raises:
            ValueError: Se `v` não estiver no formato "dia/mês/ano".
        """
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
        """Valida que ao menos um entre `since` e `candle_limit` foi informado.

        Returns:
            A própria instância validada.

        Raises:
            ValueError: Se tanto `since` quanto `candle_limit` estiverem vazios/nulos.
        """
        if not self.since and not self.candle_limit:
            raise ValueError(
                f"Since: {self.since} e Candle Limit: {self.candle_limit} estão vazios.\n"
                f"Ao menos um dos dois deve ter um valor válido."
            )

        return self


class OrderConfig(BaseModel):
    """Configurações de comportamento das ordens de compra e venda.

    Attributes:
        amount: Valor em USDT por ordem (deve ser maior que zero).
        order_type: Tipo de ordem, "market" ou "limit".
        chase_percent: Percentual de ajuste do preço para perseguição da ordem limit.
        offset_percent: Percentual de offset aplicado ao preço de entrada.
        fill_timeout: Tempo máximo, em segundos, aguardando o preenchimento da ordem.
        max_retries: Número máximo de tentativas de colocação de ordem.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    # parâmetros para comportamentos das ordens
    amount: float = Field(gt=0)
    order_type: Literal["market", "limit"]
    chase_percent: float = Field(gt=0)
    offset_percent: float = Field(gt=0)
    fill_timeout: int = Field(gt=0)
    max_retries: int = Field(gt=0)


class RiskConfig(BaseModel):
    """Configurações de gerenciamento de risco do par de trading.

    Attributes:
        stop_loss_percent: Percentual de stop loss em relação ao preço de entrada.
        take_profit_percent: Percentual de take profit em relação ao preço de entrada.
        leverage: Alavancagem utilizada na operação (deve ser maior que zero).
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    stop_loss_percent: float = Field(gt=0)
    take_profit_percent: float = Field(gt=0)
    leverage: int = Field(gt=0)


class AssetSettings(BaseModel):
    """Configuração completa de um par de trading, agregando dados, ordens e risco.

    Attributes:
        symbol: Par de trading no formato unificado ccxt (ex.: "BTC/USDT:USDT").
        sandbox: Indica se o bot deve operar no ambiente sandbox. Padrão: True.
        data: Configurações de dados históricos (candles).
        orders: Configurações de comportamento das ordens.
        risk: Configurações de gerenciamento de risco.
    """

    model_config = ConfigDict(extra="forbid")

    # Constantes fixas do projeto, não são campos de configuração.
    # ClassVar = não vem do TOML, não é validado, não é editável via TOML.
    exchange: ClassVar[str] = "binance"
    market_type: ClassVar[str] = "future"

    # Campos da classe SymbolConfig
    symbol: str
    strategy: str
    sandbox: bool = True

    # Instância das classes:
    data: DataConfig
    orders: OrderConfig
    risk: RiskConfig

    @field_validator("symbol")
    @classmethod
    def validate_symbol_format(cls, v: str) -> str:
        """Valida se o símbolo está no formato unificado do ccxt.

        Args:
            v: Símbolo a ser validado (ex.: "BTC/USDT:USDT").

        Returns:
            O mesmo valor `v`, caso esteja no formato correto.

        Raises:
            ValueError: Se `v` não contiver "/" e ":" no formato esperado pelo ccxt.
        """
        if "/" not in v or ":" not in v:
            raise ValueError(
                f"'symbol' deve estar no formato unificado do ccxt, (ex: 'BTC/USDT:USDT'), recebido: '{v}' "
            )

        return v

    @field_validator("strategy")
    @classmethod
    def validate_strategy(cls, v: str) -> str:
        """Valida se a estratégia existe no sistema.

        Args:
            v: Estratégia a ser validada (ex.: "triple-ema").

        Returns:
            A estratégia, caso a estratégia exista.

        Raises:
            ValueError: Se `v` não contiver uma estratégia válida.
        """
        if v not in VALID_STRATEGIES:
            raise ValueError(
                f"Estratégia inválida: '{v}'. Estratégias válidas: {sorted(VALID_STRATEGIES)}"
            )

        return v


def load_asset_settings(filepath: str) -> AssetSettings:
    """Carrega e valida a configuração de um par de trading a partir de um arquivo TOML.

    Args:
        filepath: Caminho para o arquivo TOML de configuração do asset.

    Returns:
        Instância de `AssetSettings` validada com os dados do arquivo.

    Raises:
        FileNotFoundError: Se o arquivo informado não existir.
        ValueError: Se o arquivo tiver erro de sintaxe TOML ou estiver vazio.
    """

    # Instancia o caminho do arquivo TOML como objeto Path
    path = Path(filepath)

    # Extrai o nome do arquivo, incluindo a extensão
    filename = path.name

    # Extrai o diretório pai onde o arquivo está localizado
    directory = path.parent

    if not path.exists():
        raise FileNotFoundError(f"Arquivo '{filename}' não encontrado em '{directory}'")

    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Erro de sintaxe no arquivo '{filename}', {e}") from e

    if not data:
        raise ValueError(f"Arquivo '{filename}' vazio.")

    return AssetSettings(**data)
