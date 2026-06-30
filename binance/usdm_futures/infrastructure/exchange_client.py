from __future__ import annotations

from typing import TYPE_CHECKING

import ccxt.async_support as ccxt

from ..domain.errors import NetworkError
from .errors import translate_ccxt_error

if TYPE_CHECKING:
    from loguru import Logger


class ExchangeClient:
    def __init__(
        self,
        exchange_name: str,
        api_key: str,
        api_secret: str,
        market_type: str,
        sandbox: bool,
        log: Logger,
    ) -> None:
        self._exchange_name = exchange_name
        self._api_key = api_key
        self._api_secret = api_secret
        self._market_type = market_type
        self._sandbox = sandbox
        self._log = log
        self._exchange: ccxt.Exchange | None = None

        try:
            self._exchange_class = getattr(ccxt, exchange_name)
        except AttributeError:
            raise AttributeError(f"Exchange '{exchange_name}' não encontrada no CCXT.")

    def _create_instance(self) -> ccxt.Exchange:
        exchange: ccxt.Exchange = self._exchange_class(
            {
                "apiKey": self._api_key,
                "secret": self._api_secret,
                "enableRateLimit": True,
                "timeout": 30000,
                "options": {
                    "defaultType": self._market_type,
                    "adjustForTimeDifference": True,
                    "recvWindow": 5000,
                },
            }
        )
        if self._sandbox:
            exchange.enable_demo_trading(True)
        return exchange

    async def _test_connection(self, exchange: ccxt.Exchange) -> bool:
        try:
            balance = await exchange.fetch_balance()
        except Exception as exc:
            self._log.error(f"Falha ao testar conexão: {translate_ccxt_error(exc)}")
            return False

        mode = "TESTNET" if self._sandbox else "REAL"
        self._log.info(
            f"Conexão OK [ {self._exchange_name.upper()}, {self._market_type} | {mode} ]"
        )

        try:
            self._log.info(f"USDT disponível: {balance['USDT']['free']}")
        except (KeyError, TypeError):
            pass

        return await self._check_position_mode(exchange)

    async def _check_position_mode(self, exchange: ccxt.Exchange) -> bool:
        try:
            result = await exchange.fetch_position_mode(params={"subType": "linear"})
        except ccxt.NotSupported as exc:
            self._log.warning(
                f"Verificação de position mode não suportada: {exc}. "
                "Confirme manualmente que a conta está em One-way mode."
            )
            return True
        except Exception as exc:
            self._log.error(
                f"Falha ao verificar position mode: {translate_ccxt_error(exc)}"
            )
            return False

        if result.get("hedged"):
            self._log.critical(
                "Conta em HEDGE MODE. Este bot só opera em ONE-WAY MODE. "
                "Corrija em: Binance Futures → Preferences → Position Mode → One-way."
            )
            return False

        self._log.info("Position mode: One-way validado.")
        return True

    async def _check_api_permissions(self, exchange: ccxt.Exchange) -> bool:
        fetch = getattr(exchange, "sapi_get_account_apirestrictions", None)
        if fetch is None:
            self._log.warning(
                "Endpoint sapi_get_account_apirestrictions indisponível. "
                "Verificação de escopo da API key ignorada."
            )
            return True

        try:
            r = await fetch()
        except ccxt.NotSupported as exc:
            self._log.warning(f"Verificação de escopo não suportada: {exc}.")
            return True
        except Exception as exc:
            self._log.error(f"Falha ao verificar escopo: {translate_ccxt_error(exc)}")
            return False

        if r.get("enableWithdrawals"):
            self._log.critical(
                "API key permite SAQUES. Desabilite 'Enable Withdrawals' "
                "na Binance → API Management."
            )
            return False

        if not r.get("enableReading"):
            self._log.critical(
                "API key sem permissão de leitura. Habilite 'Enable Reading' "
                "na Binance → API Management."
            )
            return False

        if not r.get("enableFutures"):
            self._log.critical(
                "API key sem permissão de Futures. Habilite 'Enable Futures' "
                "na Binance → API Management."
            )
            return False

        if r.get("enableSpotAndMarginTrading"):
            self._log.warning(
                "API key tem Spot/Margin habilitado. "
                "Reduza o escopo se esta key for exclusiva do bot."
            )

        self._log.info("Escopo da API key validado.")
        return True

    async def connect(self) -> ccxt.Exchange:
        if self._exchange is None:
            self._exchange = self._create_instance()
            if not await self._test_connection(self._exchange):
                await self._exchange.close()
                self._exchange = None
                raise NetworkError("Falha ao conectar com a exchange — verifique os logs.")
        return self._exchange

    async def close(self) -> None:
        if self._exchange is not None:
            await self._exchange.close()
            self._exchange = None
            self._log.info("Conexão com a exchange encerrada.")
