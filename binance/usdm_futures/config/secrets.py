from pathlib import Path
from typing import Self

from pydantic import SecretStr, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[3] / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    binance_api_key_prod: SecretStr = SecretStr("")
    binance_api_secret_prod: SecretStr = SecretStr("")
    binance_api_key_test: SecretStr = SecretStr("")
    binance_api_secret_test: SecretStr = SecretStr("")

    @property
    def binance_prod_api_key(self) -> str:
        return self.binance_api_key_prod.get_secret_value()

    @property
    def binance_prod_api_secret(self) -> str:
        return self.binance_api_secret_prod.get_secret_value()

    @property
    def binance_test_api_key(self) -> str:
        return self.binance_api_key_test.get_secret_value()

    @property
    def binance_test_api_secret(self) -> str:
        return self.binance_api_secret_test.get_secret_value()

    @model_validator(mode="after")
    def validate_at_least_one_credential_pair(self) -> Self:
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
        value = v.get_secret_value()
        if value and not value.strip():
            raise ValueError(f"{info.field_name} não pode ser somente espaços em branco.")
        return SecretStr(value.strip())
