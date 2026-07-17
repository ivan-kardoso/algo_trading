# Tarefa: criar enum `Role` para os papéis de timeframe e usá-lo em todo o sistema

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** Ignore-o completamente. O usuário fará as alterações necessárias nesse arquivo por conta própria. Não produza observações sobre ele.

## Contexto

Hoje os "papéis" dos timeframes são representados por **strings soltas** (`"signal"`, `"trend"`, `"aux_1"`, `"aux_2"`) espalhadas pelo código — como chaves de dicionário (`datasets["signal"]`, `repos["signal"]`, `timeframes[role]`), em mapeamentos (`_ROLE_TIMEFRAME_FIELDS`) e em filtros (`role != "signal"`). Strings soltas são frágeis: um typo (`"singal"`) não gera erro, apenas falha silenciosamente.

Queremos substituir essas strings por um **enum** dedicado, que dá segurança de tipo e centraliza os valores válidos.

## O enum

Criar um enum `Role` como **str-enum** (herda de `str` e `Enum`), para que funcione como string quando necessário (log, serialização) mantendo a segurança do enum.

Local sugerido: um novo arquivo em `binance/usdm_futures/domain/models/role.py` (ou no módulo de models onde os outros modelos de domínio residem — seguir a organização existente).

Definição:

```python
from enum import Enum


class Role(str, Enum):
    SIGNAL = "signal"
    TREND = "trend"
    AUX_1 = "aux_1"
    AUX_2 = "aux_2"
```

Exportá-lo no `__init__.py` do pacote de models, seguindo o padrão dos outros modelos.

## Onde substituir a string pelo enum

Substituir as strings de papel por `Role.*` em **todo o sistema, exceto no `triple_ema.py`** (regra inviolável). Pontos mapeados (não necessariamente exaustivo — procure por outros usos):

### `binance/usdm_futures/app/bootstrap.py`
- `_ROLE_TIMEFRAME_FIELDS` (linhas ~29-34): as chaves passam de `"signal"`/`"trend"`/`"aux_1"`/`"aux_2"` para `Role.SIGNAL`/`Role.TREND`/`Role.AUX_1`/`Role.AUX_2`. O tipo do dict passa a ser `dict[Role, str]`.
- O loop que monta `repos` e `timeframes` (linhas ~139-154): `repos` e `timeframes` passam a ser chaveados por `Role` (`dict[Role, MemoryRepository]` e `dict[Role, str]`).

### `binance/usdm_futures/orchestration/symbol_runner.py`
- `self._signal_repo = repos["signal"]` (linha ~89) → usar `repos[Role.SIGNAL]`.
- O filtro `role != "signal"` (linha ~91) → `role != Role.SIGNAL`.
- Ajustar os tipos das coleções de repos para `Role` como chave (`Mapping[Role, ...]`), mantendo a covariância já existente (`Mapping`).

### `binance/usdm_futures/orchestration/handlers/data.py`
- `timeframes['signal']` (linha ~53) → `timeframes[Role.SIGNAL]`.
- O loop sobre `other_repos` e `timeframes[role]` (linhas ~55-58) → `role` passa a ser `Role`.

### `binance/usdm_futures/orchestration/handlers/strategy.py`
- `datasets = {role: repo.get_dataset() for role, repo in repos.items()}` (linha ~31): as chaves já virão como `Role` (vindas dos repos), então `datasets` passa a ser `dict[Role, OHLCVData]`. Ajustar anotações de tipo conforme necessário.

### Tipos e assinaturas
- Onde houver anotações `dict[str, ...]` ou `Mapping[str, ...]` referentes a **papéis** (repos, timeframes, datasets, indicators), atualizar a chave de `str` para `Role`.
- **Atenção:** não confundir com dicionários que usam `str` para outros fins (ex.: chaves que não são papéis). Alterar apenas os que representam papel de timeframe.

## Fronteira com a estratégia (importante)

O `triple_ema.py` **não será alterado por você**. Porém, os dicionários que chegam à estratégia (`datasets` no `apply_indicators`, `indicators` no `check_signal`) passarão a ter chaves `Role` em vez de `str`. Isso é esperado e correto — o usuário ajustará o `triple_ema.py` para usar `Role`. Portanto:
- Faça o handler de estratégia entregar os dicionários chaveados por `Role`.
- O contrato `IStrategyPort` (`binance/usdm_futures/domain/ports/strategy.py`): se as assinaturas mencionam `dict[str, ...]` para datasets/indicators, atualizar para `dict[Role, ...]`. (Isto afeta a assinatura que o `triple_ema.py` implementa, mas você **não** deve editar o `triple_ema.py` — apenas o contrato.)

## Restrições

- **Não alterar, não abrir e não mencionar `triple_ema.py`.**
- Como `Role` é `str`-enum, comparações e logs que tratam o papel como texto continuam funcionando — não é necessário converter para `.value` na maioria dos casos, mas garanta que logs exibam o texto esperado (ex.: em f-strings, `Role.SIGNAL` renderiza conforme o str-enum; se aparecer algo como `Role.SIGNAL` em vez de `signal` no log, use `.value` onde for necessário para manter as mensagens atuais).
- Não introduzir dependências novas.
- Manter o comportamento funcional idêntico — esta é uma refatoração de tipo, não de lógica.

## Validação

1. O sistema inicializa e opera exatamente como antes (comportamento idêntico).
2. Não há mais strings de papel (`"signal"`, `"trend"`, `"aux_1"`, `"aux_2"`) usadas como chave/identificador fora do enum, exceto dentro do `triple_ema.py` (intocado).
3. Os dicionários de repos, timeframes, datasets e indicators são chaveados por `Role`.
4. Os logs de dataset continuam exibindo o valor do timeframe corretamente (sem vazar `Role.SIGNAL` como texto onde deveria aparecer `signal` ou o valor do timeframe).
5. `Role` está definido como `str`-enum e exportado no módulo de models.
