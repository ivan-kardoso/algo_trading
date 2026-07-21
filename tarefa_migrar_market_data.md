# Tarefa: migrar o bloco `[market_data]` do TOML do símbolo para o TOML da estratégia

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** Ignore-o completamente. Não produza observações sobre ele.

## Objetivo

Hoje os parâmetros estão espalhados entre dois arquivos TOML. Queremos consolidar: o bloco **`[market_data]`** (timeframes + `since` + `candle_limit`), que hoje vive no TOML do **símbolo** (`binance/symbol_toml/*.toml`), deve **migrar** para o TOML da **estratégia** (`binance/strategy_toml/*.toml`, ex.: `triple-ema.toml`). A justificativa: os timeframes e o histórico a baixar são decisão da estratégia, não do símbolo.

## O que migrar

Mover o bloco inteiro:
```toml
[market_data]
timeframe_1 = "1d"
timeframe_2 = "1h"
timeframe_3 = "15m"
timeframe_4 = ""
since = ""
candle_limit = 150
```
Do arquivo do símbolo para o arquivo da estratégia.

## Mudanças de código

### 1. TOMLs
- **Remover** a seção `[market_data]` de `binance/symbol_toml/btcusdt.toml`.
- **Adicionar** a seção `[market_data]` em `binance/strategy_toml/triple-ema.toml`.

### 2. Config da estratégia (`binance/usdm_futures/config/strategy_config.py`)
- Passar a carregar o bloco `[market_data]`. A forma mais limpa: reaproveitar a classe `MarketDataConfig` (hoje em `symbol_config.py`) — movê-la para um local compartilhado ou importá-la — e adicionar um campo `market_data: MarketDataConfig` ao `StrategySettings`.
- O `StrategySettings` passa a expor `market_data` (timeframes, since, candle_limit).

### 3. Config do símbolo (`binance/usdm_futures/config/symbol_config.py`)
- **Remover** o campo `market_data: MarketDataConfig` do `AssetSettings` (linha ~93).
- A classe `MarketDataConfig` (linha ~12): se for reutilizada pela estratégia, movê-la para onde fizer sentido (ex.: um módulo de config compartilhado ou o próprio `strategy_config.py`). Não deixá-la órfã nem duplicada.

### 4. Bootstrap (`binance/usdm_futures/app/bootstrap.py`)
- Hoje lê os timeframes de `asset.market_data` (linhas ~134, ~145: `getattr(asset.market_data, slot.value)` e `_resolve_candle_limit(asset.market_data, ...)`).
- Passar a ler de `strategy_settings.market_data` (o `StrategySettings` já é carregado no bootstrap, variável `strategy_settings`).
- O `_resolve_candle_limit` passa a receber o `market_data` vindo do strategy_settings.
- A montagem dos repos por `TimeframeSlot` permanece igual — muda apenas **de onde** vêm os timeframes (strategy_settings em vez de asset).

### 5. Ordem de carregamento
- Garantir que, no bootstrap, o `strategy_settings` seja carregado **antes** do ponto onde os repos são montados (hoje os repos são montados a partir de `asset.market_data`; passarão a depender de `strategy_settings.market_data`). Ajustar a ordem se necessário.

## Restrições

- **Não alterar `triple_ema.py`.**
- Não duplicar `MarketDataConfig` — mover/compartilhar, não copiar.
- Não alterar a lógica de montagem de repos nem de detecção de candle — apenas a origem dos dados de `market_data`.
- Não introduzir dependências novas.
- Manter os validadores de timeframe existentes (timeframe_1 obrigatório; 2/3/4 opcionais; vazio = None).

## Validação

1. `binance/symbol_toml/btcusdt.toml` não tem mais `[market_data]`.
2. `binance/strategy_toml/triple-ema.toml` tem o `[market_data]` completo.
3. O sistema inicializa lendo os timeframes/candle_limit do TOML da estratégia.
4. Os repos são montados corretamente a partir de `strategy_settings.market_data`.
5. Nenhuma referência remanescente a `asset.market_data` no código.
