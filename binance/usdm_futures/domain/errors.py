from __future__ import annotations


class RobotError(Exception):
    """Erro base para todos os erros do robô."""

    def __init__(self, message: str, original: Exception | None = None) -> None:
        self.original = original
        super().__init__(message)


class ExchangeError(RobotError):
    """Erro base para falhas de comunicação ou operação na exchange."""


class NetworkError(ExchangeError):
    """Falha de rede ao comunicar com a exchange."""


class AuthenticationError(ExchangeError):
    """Chave de API inválida ou sem permissão."""


class RateLimitError(ExchangeError):
    """Limite de requisições excedido."""


class BadRequestError(ExchangeError):
    """Parâmetros inválidos enviados à exchange."""


class OrderNotFoundError(ExchangeError):
    """Ordem não encontrada na exchange."""


class PositionNotFoundError(ExchangeError):
    """Posição não encontrada para o símbolo."""


class InsufficientFundsError(ExchangeError):
    """Saldo insuficiente para a operação."""


class UnexpectedExchangeError(ExchangeError):
    """Erro inesperado retornado pela exchange."""


class EmptyOHLCVError(ExchangeError):
    """Exchange respondeu sem candles novos após esgotar todas as tentativas."""


class HedgeModeError(ExchangeError):
    """Conta está em Hedge mode; bot só suporta One-way mode."""


class ApiPermissionError(ExchangeError):
    """Escopo da API key incompatível com operação segura do bot."""
