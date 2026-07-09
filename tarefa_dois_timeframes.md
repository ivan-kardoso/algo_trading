# Tarefa: suporte a dois timeframes (trend + signal) na infraestrutura de dados

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** Esse arquivo é de responsabilidade exclusiva do usuário. Ignore-o completamente. Faça toda a infraestrutura descrita abaixo nos demais arquivos. Não produza nenhuma observação, lista ou comentário sobre o `triple_ema.py`.

## Contexto

O bot roda **um único par por execução**. Hoje a estratégia usa **um** timeframe. Vamos passar a usar **dois** timeframes por par, ambos definidos no TOML do par:

- `trend_timeframe` — timeframe maior, define **contexto/tendência** (ex.: "4h").
- `signal_timeframe` — timeframe menor, define **gatilho e sinal** (ex.: "5m").

Os valores são flexíveis (hoje 4h/5m, amanhã pode ser 1h/5m). O sistema não deve fixar valores.

O `DataConfig` (em `binance/usdm_futures/config/symbol_config.py`) **já foi alterado pelo usuário** para conter os dois campos (`trend_timeframe` e `signal_timeframe`) e validá-los. **Confirme** esse estado antes de prosseguir; não refaça essa parte se já estiver feita.

## Objetivo desta tarefa

Refatorar **apenas a infraestrutura** para suportar dois datasets de candles (um por timeframe), levando os dois até a fronteira da estratégia. **Nenhuma lógica de contexto, gatilho ou sinal deve ser implementada aqui** — isso será feito depois, manualmente, pelo usuário, dentro do `triple_ema.py`.

## Decisões de arquitetura (já fechadas — seguir à risca)

1. **Dois datasets independentes de candles:** um para `trend_timeframe`, outro para `signal_timeframe`. Cada um tem seu próprio `OHLCVSource` e seu próprio `MemoryRepository`.

2. **`candle_limit` e `since` são únicos e aplicados aos dois datasets** (mesmos valores para trend e signal). Não criar limites separados por timeframe.

3. **Ritmo do ciclo:** o `signal_timeframe` (menor) dita o ritmo do loop — o bot acorda a cada candle de signal, como já faz hoje. O dataset de `trend` é atualizado **somente quando um candle de trend fecha de verdade** (detecção do fechamento real, não por multiplicador nem por estimativa). A cada ciclo, o handler de fetch:
   - atualiza **sempre** o dataset de signal;
   - verifica se um **novo candle de trend fechou** desde a última atualização do trend; se fechou, atualiza o dataset de trend; se não, não faz nada com o trend.

4. **Arranque:** na inicialização, **ambos** os datasets são baixados (download inicial do trend e do signal). Em regime, signal atualiza todo ciclo e trend só quando fecha candle.

5. **A estratégia passa a receber os dois conjuntos de dados** (trend e signal), cada um como seu próprio `IndicatorData` (ou equivalente). Ou seja, a fronteira que chama a estratégia deve fornecer os dois. Ajuste o contrato e o handler para fornecer os dois conjuntos.

## Componentes a alterar (mapa de referência — não exaustivo)

- `binance/usdm_futures/app/bootstrap.py` — hoje cria **um** `OHLCVSource` e **um** `MemoryRepository` (usa `asset.data.timeframe`, que não existe mais). Passar a criar **dois** de cada, um por timeframe, usando `asset.data.trend_timeframe` e `asset.data.signal_timeframe`. A função `_resolve_candle_limit` deve continuar funcionando (candle_limit único).
- `binance/usdm_futures/orchestration/symbol_runner.py` — hoje segura um `market_data_repo` e chama fetch/apply com ele. Passar a segurar os **dois** repositórios e orquestrar a atualização dos dois conforme a decisão 3.
- `binance/usdm_futures/orchestration/handlers/data.py` (handle_fetch_data) — passar a atualizar os dois datasets conforme a decisão 3 (signal sempre; trend só se fechou candle novo de trend).
- `binance/usdm_futures/orchestration/handlers/strategy.py` (handle_apply_strategy / handle_check_signal) — passar os dois conjuntos de dados para a estratégia.
- `binance/usdm_futures/domain/ports/strategy.py` (`IStrategyPort`) — ajustar as assinaturas de `apply_indicators` / `check_signal` para refletir os dois datasets.
- `binance/usdm_futures/market_data/memory_repository.py` e `source.py` — reutilizar como estão, apenas instanciados duas vezes (um por timeframe). Só alterar se algo impedir a dupla instância.

## Detecção do fechamento do candle de trend (decisão 3)

Para saber se "um novo candle de trend fechou desde a última atualização", use o mesmo mecanismo já existente para timeframes (o `MemoryRepository`/`OHLCVSource` já calculam `timeframe_ms` e sabem quando um candle fecha). A abordagem sugerida: guardar o timestamp do último candle de trend conhecido e, a cada ciclo, comparar; se o candle de trend corrente já fechou (avançou), atualizar o dataset de trend. Não introduza parâmetros de configuração novos para isso.

## Restrições

- **Não alterar, não abrir e não mencionar `triple_ema.py`.**
- Não implementar nenhuma regra de contexto/gatilho/sinal.
- Não criar parâmetros novos de configuração (sem multiplicador, sem limites por timeframe).
- Manter o comportamento de "um par por execução".
- Preservar os logs existentes; se precisar logar a atualização do trend, use uma linha informativa clara (ex.: "Dataset de tendência atualizado").

## Entregável e validação

1. Sistema inicializa baixando os dois datasets (trend e signal) sem erro.
2. Em regime, o dataset de signal atualiza a cada ciclo e o de trend só quando um candle de trend fecha.
3. A fronteira que chama a estratégia fornece os dois conjuntos de dados.
