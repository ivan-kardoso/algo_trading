"""Gerenciamento de credenciais privadas do bot Binance USDM Futures.

Este módulo fornece a classe `Secrets` que carrega e valida credenciais
da API Binance (testnet e produção) a partir de um arquivo `.env`.
Mantém valores sensíveis como `SecretStr` para segurança via Pydantic.
"""

# Importação para manipulação de caminhos e tipos
from pathlib import Path
from typing import Self


# Importações do Pydantic para validação e configuração de modelos
from pydantic import (
    SecretStr,
    field_validator,
    model_validator,
    ValidationInfo,
)

from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    """Credenciais privadas de acesso à API Binance USDM Futures.

    Carrega variáveis do arquivo `.env` via `pydantic-settings` e mantém
    os valores sensíveis encapsulados em `SecretStr` para evitar exposição
    acidental em logs ou rastreamentos de pilha.

    Attributes:
        binance_api_key_prod: Chave de API para o ambiente de produção (Trade Real).
        binance_api_secret_prod: Segredo de API para o ambiente de produção (Trade Real).
        binance_api_key_test: Chave de API para o ambiente de testnet (Sandbox).
        binance_api_secret_test: Segredo de API para o ambiente de testnet (Sandbox).
    """

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # =========================================================================
    # CONFIGURAÇÕES DE EXCHANGE
    # =========================================================================
    # credenciais de PRODUÇÃO (Trade Real)
    binance_api_key_prod: SecretStr = SecretStr("")
    binance_api_secret_prod: SecretStr = SecretStr("")

    # Credenciais de TESTNET (Sandbox)
    binance_api_key_test: SecretStr = SecretStr("")
    binance_api_secret_test: SecretStr = SecretStr("")

    @property
    def binance_prod_api_key(self) -> str:
        """Retorna a chave de API de produção descriptografada.

        Returns:
            Chave de API de produção como string simples.
        """

        key = self.binance_api_key_prod

        # Descriptografa e retorna o valor
        return key.get_secret_value()

    @property
    def binance_prod_api_secret(self) -> str:
        """Retorna o segredo de API de produção descriptografado.

        Returns:
            Segredo de API de produção como string simples.
        """

        secret = self.binance_api_secret_prod

        # Descriptografa e retorna o valor
        return secret.get_secret_value()

    @property
    def binance_test_api_key(self) -> str:
        """Retorna a chave de API de testnet descriptografada.

        Returns:
            Chave de API de testnet como string simples.
        """

        key = self.binance_api_key_test
        return key.get_secret_value()

    @property
    def binance_test_api_secret(self) -> str:
        """Retorna o segredo de API de testnet descriptografado.

        Returns:
            Segredo de API de testnet como string simples.
        """

        secret = self.binance_api_secret_test
        return secret.get_secret_value()

    # =========================================================================
    # VALIDAÇÕES: Verificações de integridade dos dados
    # =========================================================================
    @model_validator(mode="after")
    def validate_at_least_one_credential_pair(self) -> Self:
        """Valida se ao menos um par completo de credenciais foi definido.

        Garante que pelo menos um dos ambientes (testnet ou produção) tenha
        chave e segredo preenchidos simultaneamente.

        Returns:
            A própria instância `Secrets`, caso a validação passe.

        Raises:
            ValueError: Se nenhum par completo de credenciais estiver configurado.
        """

        test_complete = bool(
            self.binance_api_key_test.get_secret_value()
            and self.binance_api_secret_test.get_secret_value()
        )
        prod_complete = bool(
            self.binance_api_key_prod.get_secret_value()
            and self.binance_api_secret_prod.get_secret_value()
        )

        if not test_complete and not prod_complete:
            raise ValueError(
                "Nenhum par de credenciais completo foi definido. "
                "Preencha BINANCE_API_KEY_TEST e BINANCE_API_SECRET_TEST, "
                "ou BINANCE_API_KEY_PROD e BINANCE_API_SECRET_PROD."
            )

        return self

    @field_validator(
        "binance_api_key_test",
        "binance_api_secret_test",
        "binance_api_key_prod",
        "binance_api_secret_prod",
    )
    @classmethod
    def not_empty_if_set(cls, v: SecretStr, info: ValidationInfo) -> SecretStr:
        """Valida que o campo não contenha apenas espaços em branco.

        Remove espaços nas extremidades e re-encapsula o valor em `SecretStr`.

        Args:
            v: Valor do campo a ser validado.
            info: Informações sobre o campo em validação, incluindo o nome do campo.

        Returns:
            Valor do campo sem espaços nas extremidades, encapsulado em `SecretStr`.

        Raises:
            ValueError: Se o valor contiver apenas espaços em branco.
        """

        # Descriptografa para verificar conteúdo
        value = v.get_secret_value()

        # Se contém apenas espaços, lança erro de validação
        if value and not value.strip():
            raise ValueError(f"{info.field_name} não pode ser somente espaços em branco.")

        # Remove espaços nas extremidades e re-encripta
        return SecretStr(value.strip())
