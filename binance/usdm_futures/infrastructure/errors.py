import asyncio

import ccxt.async_support as ccxt

from ..domain.errors import (
    AuthenticationError,
    BadRequestError,
    ExchangeError,
    InsufficientFundsError,
    NetworkError,
    OrderNotFoundError,
    RateLimitError,
    UnexpectedExchangeError,
)

_CCXT_MAP: dict[type[Exception], type[ExchangeError]] = {
    asyncio.TimeoutError: NetworkError,
    ccxt.RateLimitExceeded: RateLimitError,   # subclasse de NetworkError — antes dela
    ccxt.NetworkError: NetworkError,
    ccxt.AuthenticationError: AuthenticationError,
    ccxt.BadRequest: BadRequestError,
    ccxt.OrderNotFound: OrderNotFoundError,
    ccxt.InsufficientFunds: InsufficientFundsError,
    ccxt.ExchangeError: UnexpectedExchangeError,  # catch-all — por último
}


def translate_ccxt_error(exc: Exception) -> ExchangeError:
    for ccxt_type, domain_type in _CCXT_MAP.items():
        if isinstance(exc, ccxt_type):
            return domain_type(str(exc), original=exc)
    return UnexpectedExchangeError(str(exc), original=exc)
