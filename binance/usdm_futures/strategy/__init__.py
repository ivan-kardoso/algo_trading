"""
Módulo de estratégia — PENDÊNCIA.

Reservado para implementação futura de lógica de estratégia e indicadores.
Não contém nenhuma regra de decisão ou sinal. A implementação deverá ser
feita em outra conversa, com apoio do chat.

Expõe apenas `NullStrategy`: implementação-placeholder de IStrategyPort
que nunca emite sinal, usada pelo bootstrap até a estratégia real existir.
"""

from .null_strategy import NullStrategy
from .triple_ema import TripleEmaStrategy

__all__ = ["NullStrategy", "TripleEmaStrategy"]
