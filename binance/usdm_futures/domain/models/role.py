from enum import Enum


class Role(str, Enum):
    SIGNAL = "signal"
    TREND = "trend"
    AUX_1 = "aux_1"
    AUX_2 = "aux_2"
