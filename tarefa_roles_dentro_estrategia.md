# Tarefa: mapeamento de papéis sai da configuração e vive dentro da estratégia

## Contexto

O `triple_ema.py` está **quebrado**: o enum `Role` foi removido do arquivo, mas o código ainda o referencia (`_is_aligned` e `check_signal`). Além disso, o arquivo não implementa o método `rhythm_slot()` exigido pelo contrato, e suas assinaturas não batem com `IStrategyPort`.

Esta tarefa corrige isso e remove o mapeamento de papéis da configuração.

## Mudança 1 — remover `[roles]` da configuração

### `binance/strategy_toml/triple-ema.toml`
Remover a seção `[roles]` inteira (o arquivo mantém apenas `name`, `[emas]` e `[market_data]`).

### `binance/usdm_futures/config/strategy_config.py`
- Remover a classe `RolesConfig` (linha ~86) e o campo `roles: RolesConfig` do `StrategySettings` (linha ~131).
- Remover imports/constantes que ficarem órfãos após isso (verificar `_VALID_SLOTS` e o import de `TimeframeSlot` — remover apenas se não forem mais usados no arquivo).

## Mudança 2 — `triple_ema.py`

### 2.1 — Enum de papéis mapeando para posições

Criar no módulo um enum que associa cada papel da estratégia à sua posição de timeframe:

```python
class Role(Enum):
    TREND = TimeframeSlot.TIMEFRAME_1
    AUX_1 = TimeframeSlot.TIMEFRAME_2
    SIGNAL = TimeframeSlot.TIMEFRAME_3
    RITMO = TimeframeSlot.TIMEFRAME_3
```

Importar `TimeframeSlot` de `..domain.models.timeframe_slot`.

### 2.2 — Assinaturas conforme o contrato

O contrato (`binance/usdm_futures/domain/ports/strategy.py`) exige:

- `apply_indicators(self, datasets: dict[TimeframeSlot, OHLCVData]) -> dict[TimeframeSlot, IndicatorData]`
- `check_signal(self, indicators: dict[TimeframeSlot, IndicatorData]) -> Literal["buy", "sell"] | None`
- `rhythm_slot(self) -> TimeframeSlot`

Ajustar as assinaturas atuais (hoje usam `dict[str, ...]` e `dict[Role, ...]`) para bater exatamente com o contrato.

Ajustar também o parâmetro `timeframes` do `__init__`: o bootstrap passa `dict[TimeframeSlot, str]`.

### 2.3 — Implementar `rhythm_slot()`

Retornar a posição definida em `Role.RITMO`.

### 2.4 — `_is_aligned` resolve papel → posição

O método recebe um `Role` e deve usar a **posição** correspondente para acessar o dicionário de indicadores (chaveado por `TimeframeSlot`) e o dicionário `self._timeframes`.

Preservar integralmente a lógica atual: as guardas (dataset ausente, dataset vazio, EMAs `None`), a chamada a `_check_alignment` e os três logs no nível `ALIGN` com o valor do timeframe.

### 2.5 — Preservar o restante

- Manter `_check_alignment` como está.
- Manter `check_signal` chamando `_is_aligned` para `Role.TREND`, `Role.SIGNAL` e `Role.AUX_1`, e retornando `None` (comportamento atual).
- Manter os atributos de estado do `__init__` (`_trend_lock_pending`, `_trend_blocked`, `_trend_released`, `_armed`) e o `_field_index`.
- Manter os acessos já corretos a `settings.emas.*`.

## Restrições

- Não alterar o contrato `IStrategyPort`, o runner, os handlers nem o bootstrap.
- Não criar regras de trading novas nem alterar a lógica de alinhamento.
- Não introduzir dependências novas.
- Atualizar a docstring do módulo se ela ficar incorreta após as mudanças.

## Validação

1. `triple-ema.toml` sem `[roles]`; `StrategySettings` sem `roles`/`RolesConfig`; nenhuma referência a `settings.roles` no projeto.
2. `triple_ema.py` define o enum `Role` mapeando papéis para `TimeframeSlot`.
3. `triple_ema.py` implementa `apply_indicators`, `check_signal` e `rhythm_slot` com as assinaturas do contrato.
4. O sistema inicializa sem erro e o runner obtém o ritmo da estratégia.
