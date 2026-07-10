# Tarefa: consolidar os logs de atualização de dataset em uma única linha-resumo

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** Ignore-o completamente. Não produza nenhuma observação sobre ele.

## Problema

Hoje, a cada ciclo de fetch, **cada** dataset atualizado gera **duas** linhas de log redundantes:

1. Uma linha genérica, sem identificação de par, emitida de dentro do repositório:
   - Arquivo: `binance/usdm_futures/market_data/memory_repository.py`, na função `update()` (atualmente linha ~112): `self._log.info(f"Dataset atualizado: {len(self._dataset)} candles.")`
2. Uma linha por dataset, emitida pelo handler de fetch:
   - Arquivo: `binance/usdm_futures/orchestration/handlers/data.py`, dentro de `handle_fetch_data` (atualmente linhas ~50 e ~55): `log.info(f"[{symbol}] Dataset de signal atualizado.")` e `log.info(f"[{symbol}] Dataset de {role} atualizado.")`

Com 4 timeframes, isso gera até 8 linhas por ciclo para dizer a mesma coisa. Queremos **uma única linha-resumo por ciclo**.

## Objetivo

Substituir todas essas linhas por **uma única linha de log por ciclo de fetch**, contendo apenas os datasets que **foram efetivamente atualizados naquele ciclo**, no formato exato descrito abaixo.

## Formato exato da linha-resumo

```
[{symbol}] Datasets atualizados: {papel} {timeframe} ({contagem}) -|- {papel} {timeframe} ({contagem})
```

Regras do formato:

- Prefixo fixo: `Datasets atualizados:` (após o `[{symbol}]`).
- Para **cada** dataset atualizado no ciclo, um segmento: `{papel} {timeframe} ({contagem})`, onde:
  - `{papel}` = o papel do timeframe: `signal`, `trend`, `aux_1` ou `aux_2`.
  - `{timeframe}` = o **valor** do timeframe (ex.: `5m`, `4h`, `1h`, `15m`), não o papel.
  - `{contagem}` = número de candles no dataset após a atualização (ex.: `155`).
- O separador entre segmentos é exatamente ` -|- ` (espaço, hífen, barra vertical, hífen, espaço).
- O separador aparece **apenas entre** segmentos — **não** no início e **não** no fim.
- Se apenas um dataset foi atualizado no ciclo, a linha tem só um segmento, sem separador.
- Somente os datasets que **realmente** foram atualizados naquele ciclo entram na linha. (Lembre: o `signal` atualiza todo ciclo; os demais só quando um candle próprio fecha.)

### Exemplos

Vários atualizados:
```
[BTC/USDT:USDT] Datasets atualizados: signal 5m (155) -|- aux_2 15m (152)
```

Só o signal:
```
[BTC/USDT:USDT] Datasets atualizados: signal 5m (155)
```

Todos:
```
[BTC/USDT:USDT] Datasets atualizados: signal 5m (150) -|- trend 4h (150) -|- aux_1 1h (150) -|- aux_2 15m (150)
```

## Implementação

1. **Remover** a linha de log genérica de `memory_repository.py` (`"Dataset atualizado: {N} candles."`). O repositório não deve mais logar isso; a responsabilidade de logar a atualização passa a ser exclusivamente do handler de fetch, na linha-resumo única.

2. **Reescrever** `handle_fetch_data` em `data.py` para, em vez de logar dentro do loop (uma linha por dataset), **coletar** os datasets efetivamente atualizados e emitir **uma única** linha-resumo ao final, no formato acima. Para cada dataset atualizado, o handler precisa obter:
   - o papel (`signal`, `trend`, `aux_1`, `aux_2`) — já disponível como chave;
   - o valor do timeframe correspondente (`5m`, `4h`, etc.);
   - a contagem de candles do dataset após a atualização.

3. **Disponibilizar o valor do timeframe e a contagem ao handler:** hoje o handler não tem o valor do timeframe nem a contagem de candles à mão. Resolva isso da forma mais limpa possível dentro da arquitetura existente. Opções aceitáveis (escolha a melhor):
   - expor no `MemoryRepository`/`IMarketDataRepository` um acessor para a contagem atual de candles (ex.: um método `candle_count()` ou similar) e para o valor do timeframe (ex.: `timeframe` legível, se ainda não existir);
   - ou passar o mapeamento papel→timeframe ao handler (o bootstrap/runner já conhece esses valores) e obter a contagem via repositório.
   Não introduza parâmetros de configuração novos no TOML. Não altere o comportamento de atualização (quem atualiza quando) — apenas o logging.

4. Se o `signal` não tiver um "papel" explícito no fluxo atual do handler (ele é tratado separadamente como `signal_repo`), trate-o no resumo com papel `signal` e o timeframe correspondente, exatamente como os demais.

## Restrições

- Não alterar o **quando/como** os datasets são atualizados — apenas a forma de logar.
- Não alterar `triple_ema.py` (ver Regra inviolável).
- Não criar parâmetros de configuração novos.
- Manter o prefixo `[{symbol}]` no início da linha, como nos demais logs do handler.
- Não tocar em outros logs do sistema (só os de atualização de dataset descritos aqui).

## Validação

1. Ciclo em que só o signal atualiza → uma linha com um único segmento, sem ` -|- `.
2. Ciclo em que vários atualizam → uma linha com os segmentos separados por ` -|- `, sem separador no início nem no fim.
3. A linha genérica antiga (`"Dataset atualizado: N candles."`) não aparece mais em lugar nenhum.
4. Cada segmento mostra papel + valor do timeframe + contagem entre parênteses.
