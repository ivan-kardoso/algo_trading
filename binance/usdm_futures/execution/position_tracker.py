from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

import ccxt.async_support as ccxt

from ..domain.ports import IPositionTracker, IProtectionOrders
from ..infrastructure.errors import translate_ccxt_error
from .order_utils import OrderUtils

if TYPE_CHECKING:
    from loguru import Logger


class PositionTracker(IPositionTracker):
    def __init__(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        utils: OrderUtils,
        protection_orders: IProtectionOrders,
        leverage: int,
        margin_usdt: float,
        fetch_positions_timeout: float,
        normalize_max_attempts: int,
        normalize_retry_delay: float,
        log: Logger,
    ) -> None:
        self._exchange = exchange
        self._symbol = symbol
        self._utils = utils
        self._protection_orders = protection_orders
        self._leverage = leverage
        self._margin_usdt = margin_usdt
        self._fetch_positions_timeout = fetch_positions_timeout
        self._normalize_max_attempts = normalize_max_attempts
        self._normalize_retry_delay = normalize_retry_delay
        self._log = log

    # -------------------------------------------------------------------------
    # Busca de dados na exchange
    # -------------------------------------------------------------------------

    async def _fetch_positions(self) -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            self._exchange.fetch_positions([self._symbol]),
            timeout=self._fetch_positions_timeout,
        ) or []

    async def _fetch_open_orders(self) -> list[dict[str, Any]]:
        """Busca todas as ordens abertas do par (regulares + condicionais).

        Binance expõe ordens condicionais em endpoint separado (/fapi/v1/algoOrder);
        CCXT acessa via params={"stop": True}. Duas variantes cobrem ambos os tipos.

        Comportamento em erro: se apenas uma variante falhar, WARNING e retorna
        o parcial. Se ambas falharem, propaga — retornar lista vazia seria
        indistinguível de "sem ordens" e dispararia recriação de SL/TP sobre
        proteção já existente (incidente C13).
        """
        orders: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        def _collect(result: list[dict[str, Any]] | None) -> None:
            if not result:
                return
            for order in result:
                order_id = str(order.get("id")) if order.get("id") is not None else None
                if order_id and order_id in seen_ids:
                    continue
                if order_id:
                    seen_ids.add(order_id)
                orders.append(order)

        param_variants: list[dict[str, Any] | None] = [None, {"stop": True}]
        last_failure: Exception | None = None
        failure_count = 0

        for params in param_variants:
            try:
                if params:
                    response = await self._exchange.fetch_open_orders(
                        self._symbol, None, None, params
                    )
                else:
                    response = await self._exchange.fetch_open_orders(self._symbol)
                _collect(response)
            except Exception as exc:
                failure_count += 1
                last_failure = exc
                domain_error = translate_ccxt_error(exc)
                self._log.warning(
                    f"[{self._symbol}] fetch_open_orders variant "
                    f"{params or 'default'} falhou: {domain_error}"
                )

        if failure_count == len(param_variants) and last_failure is not None:
            raise translate_ccxt_error(last_failure) from last_failure

        return orders

    # -------------------------------------------------------------------------
    # Detecção de ordens de proteção
    # -------------------------------------------------------------------------

    async def _detect_protection_orders(
        self, position_side: str, entry_price: float
    ) -> tuple[bool, bool]:
        has_sl = False
        has_tp = False
        open_orders = await self._fetch_open_orders()
        closing_side = (
            self._utils.SHORT_SIDE
            if position_side == self._utils.LONG_SIDE
            else self._utils.LONG_SIDE
        )

        for order in open_orders:
            if not self._utils.is_protection_order(order, closing_side):
                continue

            stop_price = self._utils.get_stop_price(order)

            if self._utils.is_take_profit_type(order):
                has_tp = True
                continue
            if self._utils.is_stop_loss_type(order):
                has_sl = True
                continue

            if stop_price is not None:
                is_sl, is_tp = self._utils.classify_by_price(
                    position_side, entry_price, stop_price
                )
                has_sl = has_sl or is_sl
                has_tp = has_tp or is_tp

        return has_sl, has_tp

    # -------------------------------------------------------------------------
    # Cancelamento de ordens
    # -------------------------------------------------------------------------

    async def _cancel_orders_individually(
        self, orders: list[dict[str, Any]] | None = None
    ) -> bool:
        if orders is None:
            orders = await self._fetch_open_orders()
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

    async def _cancel_all_orders(self) -> None:
        """Cancela todas as ordens do par. Best-effort: nunca levanta exceção."""
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

    async def _cancel_non_protection_orders(self) -> None:
        """Cancela apenas ordens que NÃO são reduceOnly (preserva SL/TP)."""
        orders = await self._fetch_open_orders()
        non_protection = [
            o for o in orders
            if not self._utils.is_truthy_flag(
                o.get("reduceOnly") or o.get("info", {}).get("reduceOnly")
            )
        ]
        if non_protection:
            await self._cancel_orders_individually(non_protection)
        else:
            self._log.info(f"[{self._symbol}] Nenhuma ordem não-proteção para cancelar.")

    # -------------------------------------------------------------------------
    # Interface pública (IPositionTracker)
    # -------------------------------------------------------------------------

    async def initialize(self) -> None:
        """Limpa ordens residuais e configura margem ISOLATED e alavancagem.

        A limpeza inicial é pré-requisito de set_margin_mode/set_leverage:
        Binance rejeita com -4067 se existirem ordens no par (cenário comum
        após crash/reboot com órfãs).

        Margem ISOLATED contém o risco ao valor da margem da posição, sem
        derramar para o saldo livre. -4046 é idempotente.
        """
        await self._cancel_all_orders()

        try:
            response = await self._exchange.set_margin_mode("ISOLATED", self._symbol)
        except ccxt.MarginModeAlreadySet:
            self._log.debug(f"[{self._symbol}] Margem já configurada como ISOLATED")
        except Exception as exc:
            raise translate_ccxt_error(exc) from exc
        else:
            if isinstance(response, dict) and response.get("code") == -4046:
                self._log.debug(f"[{self._symbol}] Margem já configurada como ISOLATED")
            else:
                self._log.info(f"[{self._symbol}] Margem configurada como ISOLATED")

        try:
            await self._exchange.set_leverage(self._leverage, self._symbol)
        except Exception as exc:
            raise translate_ccxt_error(exc) from exc

        self._log.info(f"[{self._symbol}] Alavancagem configurada: {self._leverage}x")

    async def has_active_position(self) -> bool | None:
        """Verifica se existe posição ativa para o símbolo.

        Returns:
            True se posição ativa; False se sem posição; None em caso de erro.
        """
        try:
            positions = await self._fetch_positions()
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.error(f"[{self._symbol}] Erro ao verificar posição: {domain_error}")
            return None

        active = next((p for p in positions if self._utils.extract_size(p) > 0), None)
        return active is not None

    async def normalize_position_state(self) -> bool | None:
        """Verifica e normaliza o estado da posição com retry e confirmação.

        Fluxo: detecta proteção → se incompleta, recria + confirma via endpoint
        algo → repete até N tentativas. Nunca fecha a posição a mercado: falha
        terminal retorna None para o orquestrador decidir (→ ERROR).

        Returns:
            True se posição ativa com SL/TP confirmados.
            False se não há posição (ordens não-proteção canceladas).
            None se não foi possível estabelecer proteção após retries.
        """
        try:
            positions = await self._fetch_positions()
        except Exception as exc:
            domain_error = translate_ccxt_error(exc)
            self._log.error(
                f"[{self._symbol}] Não foi possível verificar posição: {domain_error}"
            )
            return None

        active_position = next(
            (p for p in positions if self._utils.extract_size(p) > 0), None
        )

        if not active_position:
            self._log.info(
                f"[{self._symbol}] Nenhuma posição ativa. Cancelando ordens pendentes."
            )
            try:
                await self._cancel_non_protection_orders()
            except Exception as exc:
                domain_error = translate_ccxt_error(exc)
                self._log.warning(
                    f"[{self._symbol}] Falha ao cancelar ordens não-proteção: "
                    f"{domain_error}. Prosseguindo — posição não está exposta."
                )
            return False

        entry_price = self._utils.extract_entry_price(active_position)
        side = self._utils.derive_side(active_position)

        if entry_price is None or side is None:
            self._log.warning(
                f"[{self._symbol}] Posição sem dados suficientes. Cancelando ordens."
            )
            try:
                await self._cancel_non_protection_orders()
            except Exception as exc:
                domain_error = translate_ccxt_error(exc)
                self._log.warning(
                    f"[{self._symbol}] Falha ao cancelar ordens não-proteção: "
                    f"{domain_error}. Prosseguindo."
                )
            return False

        position_size = self._utils.extract_size(active_position)
        amount_for_protection = position_size if position_size > 0 else (
            self._utils.calculate_quantity_from_margin(
                self._margin_usdt, self._leverage, entry_price
            )
        )

        for attempt in range(1, self._normalize_max_attempts + 1):
            try:
                has_sl, has_tp = await self._detect_protection_orders(side, entry_price)
            except Exception as exc:
                domain_error = translate_ccxt_error(exc)
                self._log.warning(
                    f"[{self._symbol}] Detecção de proteção falhou "
                    f"(tentativa {attempt}/{self._normalize_max_attempts}): {domain_error}"
                )
                # Não recriar sem conhecer o estado real — recriação cega
                # geraria duplicatas sobre SL/TP vivos.
                if attempt < self._normalize_max_attempts:
                    await asyncio.sleep(self._normalize_retry_delay)
                continue

            if has_sl and has_tp:
                self._log.info(f"[{self._symbol}] Posição ativa. SL/TP configurados.")
                return True

            self._log.warning(
                f"[{self._symbol}] Proteção incompleta (SL: {has_sl}, TP: {has_tp}). "
                f"Recriando... (tentativa {attempt}/{self._normalize_max_attempts})"
            )

            sl_ok, tp_ok = await self._protection_orders.recreate_missing(
                side, entry_price, has_sl, has_tp, amount=amount_for_protection
            )

            if sl_ok and tp_ok:
                self._log.info(
                    f"[{self._symbol}] Posição ativa. SL/TP confirmados após recriação."
                )
                return True

            if attempt < self._normalize_max_attempts:
                await asyncio.sleep(self._normalize_retry_delay)

        self._log.critical(
            f"[{self._symbol}] Proteção não pôde ser estabelecida após "
            f"{self._normalize_max_attempts} tentativas. Sinalizando erro."
        )
        return None
