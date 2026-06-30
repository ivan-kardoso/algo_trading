from enum import Enum


class State(Enum):
    CHECK_WINDOW = "check_window"
    GET_PAIR = "get_pair"
    EXCHANGE = "exchange"
    MANAGE_ORDERS = "manage_orders"
    CLEAN_ORDERS_ORPHANS = "clean_orders_orphans"
    FETCH_DATA = "fetch_data"
    APPLY_STRATEGY = "apply_strategy"
    CHECK_SIGNAL = "check_signal"
    OPENING_POSITION = "opening_position"
    MONITORING = "monitoring"
    STANDBY = "standby"
    ERROR = "error"
    STOPPED = "stopped"


class StandbyReason(Enum):
    MARKET_CLOSED = "market_closed"
    WAIT_NEXT_CANDLE = "wait_next_candle"
