from __future__ import annotations

import asyncio
from typing import Any, Literal, TYPE_CHECKING

import ccxt.async_support as ccxt

from ..domain.ports import IOrderExecutor, IProtectionOrders
from ..infrastructure.errors import translate_ccxt_error
from .order_utils import OrderUtils

if TYPE_CHECKING:
    from loguru import Logger


class OrderExecutor(IOrderExecutor):
    def __init__(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        utils: OrderUtils,
        protection_orders: IProtectionOrders,
        margin_usdt: float,
        leverage: int,
        order_type: str,
        chase_percent: float,
        offset_percent: float,
        fill_timeout: int,
        max_retries: int,
        fetch_positions_timeout: float,
        log: Logger,
    ) -> None:
        self._exchange = exchange
        self._symbol = symbol
        self._utils = utils
        self._protection_orders = protection_orders
        self._margin_usdt = margin_usdt
        self._leverage = leverage
        self._order_type = order_type
        self._chase_percent = chase_percent
        self._offset_percent = offset_percent
        self._fill_timeout = fill_timeout
        self._max_retries = max_retries
        self._fetch_positions_timeout = fetch_positions_timeout
        self._log = log

    # -------------------------------------------------------------------------
    # Busca de dados na exchange
    # -------------------------------------------------------------------------

    async def _get_current_price(self) -> float | None:
        try:
            ticker = await self._exchange.fetch_ticker(self._symbol)
            return ticker["last"]
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.error(f"[{self._symbol}] Erro ao buscar preço: {domain_error}")
            return None

    async def _fetch_positions(self) -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            self._exchange.fetch_positions([self._symbol]),
            timeout=self._fetch_positions_timeout,
        ) or []

    async def _has_active_position(self) -> bool | None:
        try:
            positions = await self._fetch_positions()
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.error(f"[{self._symbol}] Erro ao verificar posição: {domain_error}")
            return None
        active = next((p for p in positions if self._utils.extract_size(p) > 0), None)
        return active is not None

    # -------------------------------------------------------------------------
    # Cancelamento de ordens
    # -------------------------------------------------------------------------

    async def _fetch_all_open_orders(self) -> list[dict[str, Any]]:
        """Busca ordens abertas (regulares + condicionais) para cancelamento."""
        orders: list[dict[str, Any]] = []
        seen: set[str] = set()

        for params in (None, {"stop": True}):
            try:
                if params:
                    result = await self._exchange.fetch_open_orders(
                        self._symbol, None, None, params
                    )
                else:
                    result = await self._exchange.fetch_open_orders(self._symbol)
                for o in result or []:
                    oid = str(o.get("id")) if o.get("id") is not None else None
                    if oid and oid not in seen:
                        seen.add(oid)
                        orders.append(o)
            except Exception:
                pass

        return orders

    async def _cancel_orders_individually(
        self, orders: list[dict[str, Any]] | None = None
    ) -> bool:
        if orders is None:
            orders = await self._fetch_all_open_orders()

        success = True
        for order in orders:
            try:
                try:
                    await self._exchange.cancel_order(order["id"], self._symbol)
                except Exception:
                    await self._exchange.cancel_order(
                        order["id"], self._symbol, {"stop": True}
                    )
            except Exception as exc:
                success = False
                domain_error = translate_ccxt_error(exc)
                if "Unknown order" in str(exc):
                    self._log.debug(
                        f"[{self._symbol}] Ordem já cancelada: {order.get('id')}"
                    )
                else:
                    self._log.warning(
                        f"[{self._symbol}] Falha ao cancelar ordem {order.get('id')}: {domain_error}"
                    )

        if not orders:
            self._log.info(f"[{self._symbol}] Nenhuma ordem pendente para cancelar.")

        return success

    # -------------------------------------------------------------------------
    # Envio de ordens de entrada
    # -------------------------------------------------------------------------

    async def _send_market_order(
        self,
        side: Literal["buy", "sell"],
        amount: float,
        attempt: int,
        max_retries: int,
    ) -> dict[str, Any] | None:
        order = await self._exchange.create_order(
            symbol=self._symbol,
            type="market",
            side=side,
            amount=float(self._utils.format_amount(amount)),
        )

        if not order or "id" not in order:
            return None

        filled_qty = float(order.get("filled") or 0)
        if filled_qty > 0:
            return order

        refreshed = await self._exchange.fetch_order(order["id"], self._symbol)
        filled_qty = float(refreshed.get("filled") or 0)
        if filled_qty > 0:
            return refreshed

        self._log.warning(
            f"[{self._symbol}] Ordem market não preenchida. Tentativa {attempt}/{max_retries}."
        )
        return None

    async def _send_limit_order(
        self,
        side: Literal["buy", "sell"],
        amount: float,
        current_price: float,
        attempt: int,
        max_retries: int,
    ) -> dict[str, Any] | None:
        entry_price = self._utils.calculate_entry_price(
            side, current_price, self._offset_percent
        )

        order = await self._exchange.create_order(
            symbol=self._symbol,
            type="limit",
            side=side,
            amount=float(self._utils.format_amount(amount)),
            price=entry_price,
        )

        if not order or "id" not in order:
            return None

        await asyncio.sleep(self._fill_timeout)

        refreshed = await self._exchange.fetch_order(order["id"], self._symbol)
        filled_qty = float(refreshed.get("filled") or 0)

        if filled_qty > 0:
            return refreshed

        self._log.info(
            f"[{self._symbol}] Ordem {order['id']} não executada. Cancelando..."
        )
        try:
            await self._exchange.cancel_order(order["id"], self._symbol)
        except Exception as exc:
            self._log.warning(
                f"[{self._symbol}] Falha ao cancelar ordem {order['id']}: {exc}. Verificando fill..."
            )
            refreshed = await self._exchange.fetch_order(order["id"], self._symbol)
            filled_qty = float(refreshed.get("filled") or 0)
            if filled_qty > 0:
                return refreshed

        return None

    async def _send_order(
        self, side: Literal["buy", "sell"], amount: float
    ) -> dict[str, Any] | None:
        """Envia ordem de entrada com retry e limite de perseguição de preço."""
        max_retries = self._max_retries if self._max_retries > 0 else 1

        initial_price = await self._get_current_price()
        if not initial_price or initial_price <= 0:
            self._log.error(f"[{self._symbol}] Preço inicial inválido. Abortando ordem.")
            return None

        for attempt in range(1, max_retries + 1):
            current_price = await self._get_current_price()
            if not current_price or current_price <= 0:
                self._log.warning(f"[{self._symbol}] Preço atual inválido. Abortando.")
                break

            price_deviation = abs(current_price - initial_price)
            chase_limit = initial_price * (self._chase_percent / 100)
            if price_deviation > chase_limit:
                move_pct = (price_deviation / initial_price) * 100
                self._log.warning(
                    f"[{self._symbol}] Preço se moveu {move_pct:.3f}% "
                    f"(absoluto: {price_deviation:.8g}). "
                    f"Limite: {self._chase_percent}%. Abortando."
                )
                break

            if self._order_type == "market":
                result = await self._send_market_order(side, amount, attempt, max_retries)
            else:
                result = await self._send_limit_order(
                    side, amount, current_price, attempt, max_retries
                )

            if result:
                return result

        return None

    async def _emergency_close_position(
        self, side: Literal["buy", "sell"], amount: float
    ) -> None:
        """Fecha posição a mercado em emergência (SL não confirmado após entrada)."""
        opposite_side = (
            self._utils.SHORT_SIDE
            if side == self._utils.LONG_SIDE
            else self._utils.LONG_SIDE
        )
        try:
            await self._exchange.create_order(
                symbol=self._symbol,
                type="market",
                side=opposite_side,
                amount=float(self._utils.format_amount(amount)),
                params={"reduceOnly": True},
            )
            self._log.critical(
                f"[{self._symbol}] Posição fechada a mercado (emergência). SL não confirmado."
            )
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.critical(
                f"[{self._symbol}] FALHA AO FECHAR POSIÇÃO DE EMERGÊNCIA: {domain_error}"
            )

    # -------------------------------------------------------------------------
    # Interface pública (IOrderExecutor)
    # -------------------------------------------------------------------------

    async def cancel_all_orders(self) -> None:
        """Cancela todas as ordens abertas do par (incluindo reduceOnly).

        Best-effort: engole erros internos do bulk cancel e cai em fallback
        individual. Não levanta exceções — falha parcial resulta em órfãs
        residuais mas não quebra o fluxo do bot.
        """
        try:
            await self._exchange.cancel_all_orders(self._symbol)
            self._log.info(f"[{self._symbol}] cancel_all_orders executado.")
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.debug(
                f"[{self._symbol}] cancel_all_orders falhou, cancelamento individual: {domain_error}"
            )

        try:
            await self._cancel_orders_individually()
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.warning(
                f"[{self._symbol}] Cancelamento individual falhou totalmente: "
                f"{domain_error}. Órfãs podem permanecer."
            )

    async def open_order(self, side: Literal["buy", "sell"]) -> dict[str, Any]:
        """Abre uma posição com ordem de entrada e ordens de proteção.

        Fluxo: envia ordem → reconcilia posição se necessário → cria SL com
        confirmação (crítico: emergência se falhar) → cria TP (best-effort).
        """
        if side not in self._utils.VALID_SIDES:
            raise ValueError(f"Side inválido: {side}")

        result: dict[str, Any] = {
            "success": False,
            "order": None,
            "entry_price": None,
            "sl_order": None,
            "tp_order": None,
        }

        current_price = await self._get_current_price()
        if not current_price or current_price <= 0:
            self._log.error(
                f"[{self._symbol}] Preço indisponível para calcular quantidade. Abortando ordem."
            )
            return result

        quantity = self._utils.calculate_quantity_from_margin(
            self._margin_usdt, self._leverage, current_price
        )

        min_amount = self._utils.get_min_amount()
        min_notional = self._utils.get_min_notional()
        notional = quantity * current_price
        if (min_amount is not None and quantity < min_amount) or (
            min_notional is not None and notional < min_notional
        ):
            self._log.error(
                f"[{self._symbol}] Quantidade calculada ({quantity}) abaixo do mínimo "
                f"permitido pela exchange (min_amount={min_amount}, min_notional={min_notional}). "
                f"Ordem não enviada."
            )
            return result

        order_result = await self._send_order(side, quantity)

        if not order_result or not order_result.get("id"):
            self._log.warning(
                f"[{self._symbol}] Ordem aparentemente não preenchida. Verificando posição..."
            )
            has_position = await self._has_active_position()
            if has_position is not True:
                self._log.warning(f"[{self._symbol}] Sem posição confirmada. Abortando.")
                return result

            self._log.warning(
                f"[{self._symbol}] Posição detectada apesar de ordem sem fill. "
                f"Prosseguindo com proteção."
            )
            positions = await self._fetch_positions()
            active = next(
                (p for p in positions if self._utils.extract_size(p) > 0), None
            )
            if not active:
                return result

            order_result = {
                "id": "reconciled",
                "filled": self._utils.extract_size(active),
                "status": "filled",
                "average": self._utils.extract_entry_price(active),
                "price": self._utils.extract_entry_price(active),
            }

        result["order"] = order_result

        filled_qty = float(order_result.get("filled") or 0)
        status = str(order_result.get("status") or "").lower()
        is_filled = filled_qty > 0 or status in {"closed", "filled"}

        if not is_filled:
            self._log.warning(
                f"[{self._symbol}] Ordem criada mas não preenchida. Verificando posição..."
            )
            has_position = await self._has_active_position()
            if has_position is not True:
                self._log.warning(
                    f"[{self._symbol}] Sem posição confirmada. "
                    f"[Id: {order_result.get('id')}] [Status: {status}]"
                )
                return result

            self._log.warning(
                f"[{self._symbol}] Posição detectada apesar de filled=0. "
                f"Prosseguindo com proteção."
            )
            positions = await self._fetch_positions()
            active = next(
                (p for p in positions if self._utils.extract_size(p) > 0), None
            )
            if not active:
                return result

            filled_qty = self._utils.extract_size(active)
            order_result.update({
                "filled": filled_qty,
                "status": "filled",
                "average": self._utils.extract_entry_price(active),
            })
            result["order"] = order_result

        entry_price = order_result.get("average") or order_result.get("price")

        self._log.info(
            f"[{self._symbol}] Ordem preenchida! "
            f"[Lado: {side}] [Preço: {entry_price}] [Id: {order_result['id']}]"
        )

        if entry_price is None:
            entry_price = await self._get_current_price()

        if entry_price is None:
            self._log.warning(
                f"[{self._symbol}] Preço de entrada indisponível. Não é possível criar SL/TP."
            )
            return result

        amount_for_protection = filled_qty if filled_qty > 0 else quantity

        # Cria SL com confirmação via recreate_missing (has_tp=True = não toca TP ainda).
        # recreate_missing cria + confirma internamente via endpoint algo.
        sl_ok, _ = await self._protection_orders.recreate_missing(
            side, float(entry_price),
            has_sl=False, has_tp=True,
            amount=amount_for_protection,
        )

        if not sl_ok:
            self._log.critical(
                f"[{self._symbol}] SL não confirmado. Fechando posição de emergência."
            )
            await self._emergency_close_position(side, amount_for_protection)
            return result

        # Cria TP (best-effort: posição é mantida com apenas SL se falhar).
        _, tp_ok = await self._protection_orders.recreate_missing(
            side, float(entry_price),
            has_sl=True, has_tp=False,
            amount=amount_for_protection,
        )

        if not tp_ok:
            self._log.warning(
                f"[{self._symbol}] TP falhou, mas SL está ativo. Posição mantida."
            )

        result.update({
            "success": True,
            "entry_price": float(entry_price),
        })

        return result
