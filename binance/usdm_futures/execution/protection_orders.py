from __future__ import annotations

import asyncio
from typing import Any, Literal, cast, TYPE_CHECKING

import ccxt.async_support as ccxt

from ..domain.ports import IProtectionOrders
from ..infrastructure.errors import translate_ccxt_error
from .order_utils import OrderUtils

if TYPE_CHECKING:
    from loguru import Logger


class ProtectionOrders(IProtectionOrders):
    # SL/TP na Binance Futures são roteados pelo CCXT para /fapi/v1/algoOrder.
    # O id retornado é um algoId — fetch_order precisa de params={"stop": True}
    # para bater no endpoint correto.
    _DEAD_ORDER_STATUSES = {"canceled", "expired", "rejected"}

    def __init__(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        utils: OrderUtils,
        percent_sl: float,
        percent_tp: float,
        sl_confirm_attempts: int,
        sl_confirm_delay: float,
        log: Logger,
    ) -> None:
        self._exchange = exchange
        self._symbol = symbol
        self._utils = utils
        self._percent_sl = percent_sl
        self._percent_tp = percent_tp
        self._sl_confirm_attempts = sl_confirm_attempts
        self._sl_confirm_delay = sl_confirm_delay
        self._log = log

    async def _create_protection_order(
        self,
        side: Literal["buy", "sell"],
        entry_price: float,
        order_type: str,
        percent: float,
        is_stop_loss: bool,
        amount: float,
    ) -> dict[str, Any] | None:
        protection_price = self._utils.calculate_protection_price(
            side, entry_price, percent, is_stop_loss
        )
        order_name = "Stop Loss" if is_stop_loss else "Take Profit"
        opposite_side = (
            self._utils.SHORT_SIDE
            if side == self._utils.LONG_SIDE
            else self._utils.LONG_SIDE
        )

        try:
            order = await self._exchange.create_order(
                symbol=self._symbol,
                type=cast(Any, order_type),
                side=opposite_side,
                amount=float(self._utils.format_amount(amount)),
                params={"stopPrice": protection_price, "reduceOnly": True},
            )
            self._log.info(f"[{self._symbol}] {order_name} criado: {protection_price}")
            return order
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.error(
                f"[{self._symbol}] Falha ao criar {order_name} em {protection_price}: {domain_error}"
            )
            return None

    async def _confirm_protection_order(self, order: dict[str, Any] | None) -> bool:
        """Confirma que a ordem de proteção (SL/TP) está viva na exchange.

        Usa params={"stop": True} pois o id é um algoId — sem esse param, CCXT
        roteia para /fapi/v1/order e Binance responde -2013 (falso negativo).
        """
        if not order or not order.get("id"):
            return False

        order_id = order["id"]
        for attempt in range(1, self._sl_confirm_attempts + 1):
            try:
                fetched = await self._exchange.fetch_order(
                    order_id, self._symbol, {"stop": True}
                )
                status = str((fetched or {}).get("status") or "").lower()
                if fetched and status not in self._DEAD_ORDER_STATUSES:
                    return True
                self._log.debug(
                    f"[{self._symbol}] Confirmação SL tentativa {attempt}: status='{status}'"
                )
            except Exception as exc:
                domain_error = translate_ccxt_error(exc)
                self._log.debug(
                    f"[{self._symbol}] Confirmação SL tentativa {attempt} falhou: {domain_error}"
                )

            if attempt < self._sl_confirm_attempts:
                await asyncio.sleep(self._sl_confirm_delay)

        return False

    async def send_protection_orders(
        self,
        side: Literal["buy", "sell"],
        entry_price: float,
        amount: float | None = None,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        effective_amount = amount if amount is not None else 0.0
        sl_order = await self._create_protection_order(
            side, entry_price, "stop_market", self._percent_sl,
            is_stop_loss=True, amount=effective_amount,
        )
        tp_order = await self._create_protection_order(
            side, entry_price, "take_profit_market", self._percent_tp,
            is_stop_loss=False, amount=effective_amount,
        )
        return sl_order, tp_order

    async def recreate_missing(
        self,
        side: Literal["buy", "sell"],
        entry_price: float,
        has_sl: bool,
        has_tp: bool,
        amount: float,
    ) -> tuple[bool, bool]:
        """Recria ordens de proteção faltantes e confirma cada criação.

        Returns:
            (sl_ok, tp_ok): True se a proteção está presente e confirmada;
            False se criação ou confirmação falhou.
        """
        sl_ok = has_sl
        tp_ok = has_tp

        if not has_sl:
            sl_order = await self._create_protection_order(
                side, entry_price, "stop_market", self._percent_sl,
                is_stop_loss=True, amount=amount,
            )
            if sl_order and await self._confirm_protection_order(sl_order):
                sl_ok = True
            else:
                self._log.warning(
                    f"[{self._symbol}] Stop Loss não confirmado após recriação."
                )

        if not has_tp:
            tp_order = await self._create_protection_order(
                side, entry_price, "take_profit_market", self._percent_tp,
                is_stop_loss=False, amount=amount,
            )
            if tp_order and await self._confirm_protection_order(tp_order):
                tp_ok = True
            else:
                self._log.warning(
                    f"[{self._symbol}] Take Profit não confirmado após recriação."
                )

        return sl_ok, tp_ok
