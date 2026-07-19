# Tarefa: desacoplar papéis de timeframe do sistema (papéis passam a ser da estratégia)

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** O usuário fará todas as alterações nesse arquivo. Ignore-o completamente e não produza observações sobre ele. Onde a mudança encostar na estratégia, ajuste apenas o **contrato** (`IStrategyPort`) e a **fronteira** (handlers/bootstrap), nunca o `triple_ema.py`.

## Objetivo geral

Hoje o sistema conhece "papéis" de timeframe (`signal`, `trend`, `aux_1`, `aux_2`) via enum `Role`, e o TOML do símbolo define timeframes já com papel (`signal_timeframe`, etc.). O `signal` é tratado como especial pelo sistema (dita o ritmo do loop e é atualizado todo ciclo).

Queremos **desacoplar papel do sistema**: papel passa a ser um conceito **interno da estratégia**. O sistema passa a trabalhar com timeframes **por posição** (`timeframe_1`..`timeframe_4`), sem saber o que cada um significa. Quem dita o ritmo do loop passa a ser informado **pela estratégia** (via contrato), não assumido pelo sistema.

## Mudança 1 — TOML do símbolo: timeframes por posição

No TOML do par (`binance/symbol_toml/*.toml`):
- Renomear a seção `[data]` para `[market_data]`.
- Substituir os campos com papel pelos campos por posição:
  ```toml
  [market_data]
  timeframe_1 = "1d"     # obrigatório
  timeframe_2 = "1h"     # opcional
  timeframe_3 = "15m"    # opcional
  timeframe_4 = ""       # opcional
  since = ""
  candle_limit = 150
  ```
- `timeframe_1` é **obrigatório**; `timeframe_2/3/4` são **opcionais** (vazio = ausente).

### DataConfig (`binance/usdm_futures/config/symbol_config.py`)
- Renomear a classe/uso conforme a seção (`DataConfig` pode manter o nome ou virar `MarketDataConfig` — escolher o mais coerente e ajustar o `load`/referências).
- Campos: `timeframe_1: str` (obrigatório); `timeframe_2/3/4: str | None = None` (opcionais). Manter `since` e `candle_limit`.
- Adaptar o validador de timeframe para os campos novos (tratando string vazia como `None`, como já faz hoje).
- Ajustar o ponto do config do símbolo que referencia a seção (o atributo `asset.data` passa a `asset.market_data`, ou equivalente).

## Mudança 2 — TOML da estratégia: mapeamento posição→papel + ritmo

No TOML da estratégia (`binance/strategy_toml/triple-ema.toml`), adicionar:
- O **mapeamento** de cada papel da estratégia para uma **posição** de timeframe do símbolo. Ex.:
  ```toml
  signal = "timeframe_3"
  trend = "timeframe_1"
  # aux_1, aux_2 opcionais, se a estratégia os usar
  ```
- O **ritmo** — campo **independente** que aponta para a posição de timeframe que dita o ritmo do loop:
  ```toml
  ritmo = "timeframe_3"
  ```
  (o ritmo é independente do signal; pode apontar para qualquer posição preenchida.)

### StrategySettings (`binance/usdm_futures/config/strategy_config.py`)
- Adicionar campos para o mapeamento posição→papel e para o `ritmo`.
- Validar que `ritmo` referencia uma posição válida (`timeframe_1`..`timeframe_4`).
- **Importante:** a interpretação de quais papéis existem e como se mapeiam é da estratégia. O `StrategySettings` apenas carrega e disponibiliza esses dados; não deve embutir lógica específica de papéis do sistema. Modelar de forma que a estratégia (triple_ema, alterada pelo usuário depois) consiga ler o mapeamento e o ritmo.

## Mudança 3 — sistema passa a trabalhar por posição

O enum `Role` deixa de ser usado pelo **sistema**. O sistema passa a chavear repos, timeframes e datasets por **posição** (uma string/identificador `"timeframe_1"`..`"timeframe_4"`, ou um enum `TimeframeSlot` equivalente — escolher a abordagem mais limpa; se criar um enum de posição, defini-lo em `domain/models`).

### Bootstrap (`binance/usdm_futures/app/bootstrap.py`)
- Remover o `_ROLE_TIMEFRAME_FIELDS` (mapa papel→campo). Passar a iterar sobre as **posições** (`timeframe_1`..`timeframe_4`) do `market_data`, criando um `OHLCVSource` + `MemoryRepository` por posição **preenchida**.
- `repos` e `timeframes` passam a ser chaveados por **posição**.
- Não passar mais papéis ao runner; passar as posições.

### Runner (`binance/usdm_futures/orchestration/symbol_runner.py`)
- Hoje usa `repos[Role.SIGNAL]` como o repo de ritmo e separa `other_repos` por `role != Role.SIGNAL`. Substituir por: o **repo de ritmo** é determinado pela **posição de ritmo informada pela estratégia** (ver Mudança 4). Os demais repos são "os outros".
- O runner obtém a posição de ritmo da estratégia (via o método novo do contrato) e usa o repo daquela posição para o ritmo do loop (o `seconds_until_next_candle` e a atualização a cada ciclo).

### Handler de fetch (`binance/usdm_futures/orchestration/handlers/data.py`)
- Hoje `signal_repo` (ritmo) é atualizado sempre e `other_repos` só ao fechar candle. Generalizar: o **repo de ritmo** (a posição de ritmo) é atualizado sempre; os demais só quando um candle próprio fecha. A lógica de detecção de candle fechado permanece; muda apenas que o "repo de ritmo" vem da posição de ritmo, não de `Role.SIGNAL`.
- Os logs de dataset continuam mostrando o **valor do timeframe** (ex.: "15m"), como hoje.

### Handler de estratégia (`binance/usdm_futures/orchestration/handlers/strategy.py`)
- Os datasets entregues à estratégia passam a ser chaveados por **posição** (`timeframe_1`..`timeframe_4`), apenas as preenchidas.

## Mudança 4 — contrato expõe o ritmo

No contrato `binance/usdm_futures/domain/ports/strategy.py` (`IStrategyPort`):
- Alterar as assinaturas de `apply_indicators`/`check_signal` para receber os datasets/indicadores chaveados por **posição** (não mais por `Role`).
- Adicionar um método que informe ao sistema qual **posição de timeframe dita o ritmo** do loop. Ex.: `rhythm_slot() -> <posição>` (nome à escolha, coerente com o projeto). O runner chama esse método para saber qual repo usar como ritmo.

**Nota:** o `triple_ema.py` implementa esse contrato, mas **não deve ser alterado por você** — o usuário o ajustará. Apenas defina o contrato e faça o restante do sistema consumi-lo.

## Sobre o enum `Role`

- O `Role` (`domain/models/role.py`) deixa de ser usado pelo **sistema**. Se após a refatoração ele não for mais referenciado por nenhum arquivo fora do `triple_ema.py`, **não o exclua** (o usuário poderá movê-lo para dentro da estratégia). Apenas remova os usos no sistema (bootstrap, runner, handlers, contrato), substituindo por posição.
- Não crie dependência do sistema em `Role`.

## Restrições

- **Não alterar, não abrir e não mencionar `triple_ema.py`.**
- Não alterar a lógica de negócio da estratégia — apenas a infraestrutura, config e contrato.
- Não introduzir dependências novas.
- Manter o comportamento de detecção de candle fechado e "um par por execução".
- Manter os logs de dataset exibindo o valor do timeframe.

## Validação

1. O TOML do símbolo usa `[market_data]` com `timeframe_1`(obrigatório)..`timeframe_4`(opcionais), `since`, `candle_limit`.
2. O TOML da estratégia carrega o mapeamento posição→papel e o `ritmo`.
3. O sistema (bootstrap, runner, handlers) trabalha por posição, sem referências a `Role`.
4. O contrato expõe o método de ritmo; o runner usa a posição de ritmo informada para acordar o loop.
5. Rodando com só `timeframe_1` preenchido: um dataset, sistema opera. Com vários: cada um atualiza no seu ritmo (o de ritmo sempre; os outros ao fechar candle).
6. Nenhum uso de `Role` fora do `triple_ema.py`.
