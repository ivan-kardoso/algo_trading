"""Configurações do sistema do bot Binance USDM Futures.

Este módulo fornece a classe `SystemConfig` que centraliza parâmetros
de comportamento, retry, timeouts e logging do bot. Valida dados via
Pydantic e carrega configurações do arquivo `system_config.toml`.
"""

import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FetchConfig(BaseModel):
    """Configurações de comportamento de download/fetch de candles.

    Attributes:
        fetch_retry_attempts: Número máximo de tentativas de retry ao buscar candles.
        fetch_retry_delay: Tempo de espera, em segundos, entre tentativas de retry.
        batch_limit: Quantidade máxima de candles buscados por requisição.
        max_rows: Quantidade máxima de linhas mantidas em memória/armazenamento.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    # comportamento de download/fetch de candles
    fetch_retry_attempts: int = Field(gt=0)
    fetch_retry_delay: int = Field(gt=0)
    batch_limit: int = Field(gt=0)
    max_rows: int = Field(gt=0)


class MonitoringConfig(BaseModel):
    """Configurações de monitoramento de posição usadas no loop principal do bot.

    Attributes:
        max_monitoring_failures: Número máximo de falhas de monitoramento toleradas.
        monitoring_heartbeat_every: Intervalo, em ciclos, entre heartbeats de monitoramento.
        monitoring_check_interval_seconds: Intervalo, em segundos, entre verificações de
            monitoramento.
        error_wait_seconds: Tempo de espera, em segundos, após um erro de monitoramento.
        cleanup_max_retries: Número máximo de tentativas de limpeza (cleanup) em caso de falha.
        error_max_retries: Número máximo de tentativas de recuperação após erro.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    # monitoramento de posição (loop principal do bot)
    max_monitoring_failures: int = Field(gt=0)
    monitoring_heartbeat_every: int = Field(gt=0)
    monitoring_check_interval_seconds: int = Field(gt=0)
    error_wait_seconds: int = Field(gt=0)
    cleanup_max_retries: int = Field(gt=0)
    error_max_retries: int = Field(gt=0)


class ExecutionConfig(BaseModel):
    """Configurações de execução e confirmação de ordens.

    Cobre confirmação de stop loss/take profit (SL/TP) e normalização de estado.

    Attributes:
        sl_confirm_attempts: Número máximo de tentativas de confirmação do stop loss.
        sl_confirm_delay_seconds: Tempo de espera, em segundos, entre tentativas de
            confirmação do stop loss.
        fetch_positions_timeout_seconds: Tempo limite, em segundos, para buscar posições.
        normalize_max_attempts: Número máximo de tentativas de normalização de estado.
        normalize_retry_delay_seconds: Tempo de espera, em segundos, entre tentativas de
            normalização de estado.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    # execução e confirmação de ordens (SL/TP, normalização de estado)
    sl_confirm_attempts: int = Field(gt=0)
    sl_confirm_delay_seconds: float = Field(gt=0)
    fetch_positions_timeout_seconds: float = Field(gt=0)
    normalize_max_attempts: int = Field(gt=0)
    normalize_retry_delay_seconds: float = Field(gt=0)


class LoggingConfig(BaseModel):
    """Configurações de logging do bot.

    Attributes:
        log_max_bytes: Tamanho máximo, em bytes, de cada arquivo de log (mínimo 3MB).
        log_backup_count: Número de arquivos de log de backup mantidos na rotação.
        console_refresh_per_second: Taxa de atualização, por segundo, do console de logs.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    log_max_bytes: int = Field(gt=3145728)  # min 3MB
    log_backup_count: int = Field(gt=0)
    console_refresh_per_second: int = Field(gt=0)


class SystemSettings(BaseModel):
    """Configuração global do bot, agregando todas as seções de configuração.

    Attributes:
        timezone: Fuso horário usado pelo bot (ex.: "America/Sao_Paulo").
        fetch: Configurações de download/fetch de candles.
        monitoring: Configurações de monitoramento de posição.
        execution: Configurações de execução e confirmação de ordens.
        logging: Configurações de logging.
    """

    # Rejeita campos não declarados na classe, em vez de ignorá-los silenciosamente.
    # Garante que erros de digitação ou chaves obsoletas no TOML sejam detectados aqui.
    model_config = ConfigDict(extra="forbid")

    timezone: str = "America/Sao_Paulo"

    fetch: FetchConfig
    monitoring: MonitoringConfig
    execution: ExecutionConfig
    logging: LoggingConfig

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Valida se o fuso horário informado é reconhecido pelo `zoneinfo`.

        Args:
            v: Nome do fuso horário a ser validado (ex.: "America/Sao_Paulo").

        Returns:
            O mesmo valor `v`, caso seja um fuso horário válido.

        Raises:
            ValueError: Se `v` não corresponder a um fuso horário reconhecido.
        """
        try:
            ZoneInfo(v)
            return v
        except ZoneInfoNotFoundError as e:
            raise ValueError(
                f"Timezone inválido: '{v}'. Exemplo válido: 'America/Sao_paulo'"
            ) from e


def load_system_settings(filepath: str) -> SystemSettings:
    """Carrega e valida a configuração global do bot a partir de um arquivo TOML.

    Args:
        filepath: Caminho para o arquivo TOML de configuração.

    Returns:
        Instância de `GlobalConfig` validada com os dados do arquivo.

    Raises:
        FileNotFoundError: Se o arquivo informado não existir.
        ValueError: Se o arquivo tiver erro de sintaxe TOML ou estiver vazio.
    """

    path = Path(filepath)
    filename = path.name
    directory = path.parent

    if not path.exists():
        raise FileNotFoundError(f"Arquivo '{filename}' não encontrado em '{directory}'")

    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"Erro de sintaxe no arquivo '{filename}', {e}") from e

    if not data:
        raise ValueError(f"Arquivo '{filename}' vazio")

    return SystemSettings(**data)
