from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

import ccxt.async_support as ccxt


class OrderUtils:
    LONG_SIDE: Literal["buy"] = "buy"
    SHORT_SIDE: Literal["sell"] = "sell"
    VALID_SIDES: tuple[Literal["buy"], Literal["sell"]] = ("buy", "sell")

    def __init__(self, exchange: ccxt.Exchange, symbol: str) -> None:
        self._exchange = exchange
        self._symbol = symbol

    # -------------------------------------------------------------------------
    # Cálculos de preço e formatação
    # -------------------------------------------------------------------------

    def format_amount(self, amount: float) -> str:
        precision = self._exchange.amount_to_precision(self._symbol, amount)
        return precision if precision is not None else str(Decimal(str(amount)))

    def calculate_entry_price(
        self, side: str, current_price: float, offset_percent: float
    ) -> str:
        if current_price <= 0:
            raise ValueError(f"current_price deve ser positivo, recebido: {current_price}")

        price = Decimal(str(current_price))
        offset = Decimal(str(offset_percent)) / 100

        if side == self.LONG_SIDE:
            result = price * (1 - offset)
        else:
            result = price * (1 + offset)

        precision = self._exchange.price_to_precision(self._symbol, float(result))
        return precision if precision is not None else str(result)

    def calculate_protection_price(
        self, side: str, entry_price: float, percent: float, is_stop_loss: bool
    ) -> str:
        if entry_price <= 0:
            raise ValueError(f"entry_price deve ser positivo, recebido: {entry_price}")

        is_long = side == self.LONG_SIDE
        should_subtract = (is_long and is_stop_loss) or (not is_long and not is_stop_loss)

        price = Decimal(str(entry_price))
        pct = Decimal(str(percent)) / 100

        result = price * (1 - pct) if should_subtract else price * (1 + pct)

        precision = self._exchange.price_to_precision(self._symbol, float(result))
        return precision if precision is not None else str(result)

    # -------------------------------------------------------------------------
    # Extração de dados de posição
    # -------------------------------------------------------------------------

    def extract_entry_price(self, position: dict[str, Any]) -> float | None:
        info = position.get("info", {})
        candidates = [
            position.get("entryPrice"),
            info.get("entryPrice"),
            info.get("avgEntryPrice"),
        ]
        raw = next((v for v in candidates if v is not None), None)
        if raw is None:
            return None
        try:
            price = float(raw)
            return price if price > 0 else None
        except (TypeError, ValueError):
            return None

    def extract_size(self, position: dict[str, Any]) -> float:
        contracts = position.get("contracts") or position.get("info", {}).get("positionAmt")
        try:
            return abs(float(contracts or 0))
        except (TypeError, ValueError):
            return 0.0

    def derive_side(self, position: dict[str, Any]) -> str | None:
        side = position.get("side") or position.get("info", {}).get("positionSide")
        if side:
            side = str(side).lower()
            if side in ("long", "buy"):
                return self.LONG_SIDE
            if side in ("short", "sell"):
                return self.SHORT_SIDE

        contracts = position.get("contracts") or position.get("info", {}).get("positionAmt")
        try:
            value = float(contracts)
            if value > 0:
                return self.LONG_SIDE
            if value < 0:
                return self.SHORT_SIDE
        except (TypeError, ValueError):
            pass

        return None

    # -------------------------------------------------------------------------
    # Detecção e classificação de ordens de proteção
    # -------------------------------------------------------------------------

    @staticmethod
    def is_truthy_flag(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return str(value).lower() not in ("false", "0", "")

    def is_protection_order(self, order: dict[str, Any], closing_side: str) -> bool:
        reduce_only_raw = order.get("reduceOnly")
        if reduce_only_raw is None:
            reduce_only_raw = order.get("info", {}).get("reduceOnly")
        if not self.is_truthy_flag(reduce_only_raw):
            return False

        order_side = (
            order.get("side") or order.get("info", {}).get("side") or ""
        ).lower()

        if order_side and order_side not in self.VALID_SIDES:
            if "sell" in order_side:
                order_side = self.SHORT_SIDE
            elif "buy" in order_side:
                order_side = self.LONG_SIDE

        return not order_side or order_side == closing_side

    @staticmethod
    def is_take_profit_type(order: dict[str, Any]) -> bool:
        info = order.get("info", {})
        candidates = [order.get("type"), info.get("type"), info.get("origType")]
        return any("take_profit" in str(t).lower() for t in candidates if t)

    @staticmethod
    def is_stop_loss_type(order: dict[str, Any]) -> bool:
        info = order.get("info", {})
        candidates = [order.get("type"), info.get("type"), info.get("origType")]
        return any(
            "stop" in str(t).lower() and "take_profit" not in str(t).lower()
            for t in candidates
            if t
        )

    @staticmethod
    def get_stop_price(order: dict[str, Any]) -> float | None:
        raw = order.get("stopPrice") or order.get("info", {}).get("stopPrice")
        if raw is None:
            raw = (
                order.get("price")
                if order.get("type") in {"take_profit", "TAKE_PROFIT"}
                else None
            )
        if raw is not None:
            try:
                return float(raw)
            except (TypeError, ValueError):
                pass
        return None

    @staticmethod
    def classify_by_price(
        position_side: str, entry_price: float, stop_price: float
    ) -> tuple[bool, bool]:
        is_sl = False
        is_tp = False

        if position_side == "buy":
            if stop_price < entry_price:
                is_sl = True
            elif stop_price > entry_price:
                is_tp = True
        else:
            if stop_price > entry_price:
                is_sl = True
            elif stop_price < entry_price:
                is_tp = True

        return is_sl, is_tp
