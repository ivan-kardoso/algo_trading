# Tarefa: suporte dinâmico a múltiplos timeframes (1 a 4)

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** Esse arquivo é de responsabilidade exclusiva do usuário. Ignore-o completamente. Faça toda a infraestrutura descrita abaixo nos demais arquivos. Não produza nenhuma observação, lista ou comentário sobre o `triple_ema.py`.

## Contexto

O bot roda **um único par por execução**. Hoje o sistema usa **um único timeframe** (`DataConfig.timeframe`, um `OHLCVSource` e um `MemoryRepository` no bootstrap). Vamos evoluir para suportar **de 1 a 4 timeframes por par**, de forma **dinâmica**: o sistema opera apenas com os timeframes efetivamente preenchidos no TOML.

## Definição dos campos no TOML do par

O TOML do par (`binance/symbol_toml/btcusdt.toml`), na seção de dados (`[data]`), passa a ter **quatro** campos de timeframe:

- `signal_timeframe` — **OBRIGATÓRIO**. É o timeframe menor, que **dita o ritmo do loop** (o bot acorda a cada candle de signal). Sem ele o sistema não funciona.
- `trend_timeframe` — **OPCIONAL**.
- `aux_timeframe_1` — **OPCIONAL**.
- `aux_timeframe_2` — **OPCIONAL**.

Campos opcionais ausentes/None significam que aquele timeframe **não existe** para o sistema. O sistema deve se comportar como se ele nunca tivesse sido definido — **zero processamento, zero download, zero dataset** para timeframes não preenchidos. Nunca criar estruturas vazias ou "placeholders" para timeframes ausentes.

Substituir o campo atual `timeframe` por esses quatro campos.

## Comportamento dinâmico (essência da tarefa)

1. **Só existe o que foi carregado.** Para cada timeframe preenchido no TOML (incluindo obrigatoriamente o `signal`), o sistema cria **um** `OHLCVSource` + **um** `MemoryRepository` dedicado. Timeframes não preenchidos não geram nenhuma estrutura.

2. **Ritmo de atualização:**
   - o `signal_timeframe` atualiza o seu dataset **a cada ciclo** (todo candle de signal);
   - **todos os outros** timeframes preenchidos (`trend`, `aux_1`, `aux_2`) atualizam o dataset deles **somente quando um candle próprio fecha de verdade** (detecção do fechamento real por comparação de timestamp — sem multiplicador, sem parâmetro novo).

3. **A cada ciclo (a cada candle de signal):** o sistema atualiza o dataset de signal e, em seguida, percorre os demais timeframes preenchidos verificando, por comparação de timestamp, se um candle novo daquele timeframe fechou desde a última atualização. Se fechou, atualiza o dataset daquele timeframe; se não, não faz nada. A verificação é barata (comparação de timestamp) e não deve disparar download desnecessário — o download só ocorre para o timeframe que efetivamente fechou candle.

4. **Arranque:** na inicialização, todos os timeframes preenchidos têm seu dataset baixado (download inicial). Em regime, vale a regra do item 2.

## Configuração compartilhada

- `candle_limit` e `since` permanecem **únicos** e aplicam-se a **todos** os timeframes preenchidos (mesmos valores para cada dataset). Não criar limites por timeframe.

## Componentes a alterar (mapa de referência)

- **`binance/usdm_futures/config/symbol_config.py` (`DataConfig`)**: substituir o campo `timeframe` pelos quatro campos (`signal_timeframe` obrigatório; `trend_timeframe`, `aux_timeframe_1`, `aux_timeframe_2` opcionais, default None). O validador de timeframe (`VALID_TIMEFRAMES`) deve validar **cada campo preenchido**, ignorando os None. Manter as validações existentes de `since`/`candle_limit`.

- **`binance/usdm_futures/app/bootstrap.py`**: hoje cria um `OHLCVSource` e um `MemoryRepository` a partir de `asset.data.timeframe`. Passar a criar, dinamicamente, **um par (source + repo) por timeframe preenchido**. A estrutura resultante deve permitir identificar cada repositório pelo seu papel (signal / trend / aux_1 / aux_2) — por exemplo, um dicionário papel→repositório contendo apenas os papéis preenchidos. `_resolve_candle_limit` continua válido (candle_limit único).

- **`binance/usdm_futures/orchestration/symbol_runner.py`**: hoje segura um único `market_data_repo` (`self._repo`). Passar a segurar a **coleção** de repositórios preenchidos e orquestrar a atualização conforme a regra de ritmo (signal sempre; demais só ao fechar candle). O runner precisa saber qual é o repositório de `signal` (para ritmo) e iterar sobre os demais.

- **`binance/usdm_futures/orchestration/handlers/data.py` (`handle_fetch_data`)**: hoje atualiza um único `repo`. Passar a: atualizar o repositório de `signal` sempre; e, para cada outro repositório preenchido, verificar se fechou candle novo e atualizar apenas nesse caso. Logar de forma clara qual dataset foi atualizado (ex.: incluir o papel/timeframe na mensagem), para o usuário distinguir signal de trend/aux nos logs.

- **`binance/usdm_futures/market_data/memory_repository.py` / `source.py`**: reutilizar como estão, apenas instanciados uma vez por timeframe. Se for necessário expor o timestamp do último candle conhecido (para a detecção de "fechou candle novo"), adicionar um acessor mínimo, sem alterar o comportamento existente.

- **`binance/usdm_futures/orchestration/handlers/strategy.py`**: a estratégia deverá receber os datasets dos timeframes preenchidos. Ajustar o handler para fornecer, à estratégia, o conjunto de datasets disponíveis (mapeado por papel), contendo apenas os preenchidos. **Não implementar nenhuma regra de estratégia** e **não tocar no `triple_ema.py`** (ver Regra inviolável) — apenas ajustar a fronteira que entrega os dados.

## Detecção de "candle novo fechou" (para os não-signal)

Usar o mecanismo já existente de timeframe (`OHLCVSource.timeframe_ms` / lógica de fechamento de candle). Guardar, por repositório, o timestamp do último candle conhecido; a cada ciclo, comparar com o candle corrente daquele timeframe; se avançou (fechou candle novo), atualizar o dataset. Não introduzir parâmetros de configuração novos.

## Restrições

- **Não alterar, não abrir e não mencionar `triple_ema.py`.**
- Não implementar nenhuma regra de contexto/gatilho/sinal.
- Não criar parâmetros novos de configuração (sem multiplicador, sem limites por timeframe).
- Timeframes não preenchidos = inexistentes: nenhum processamento, download ou estrutura para eles.
- Manter "um par por execução".

## Entregável e validação

1. Rodando com **apenas** `signal_timeframe` preenchido: o sistema baixa e mantém **um** dataset, funciona normalmente, e não cria nenhuma estrutura para os demais.
2. Rodando com `signal` + `trend`: dois datasets; signal atualiza todo ciclo, trend só ao fechar candle de trend.
3. Rodando com os quatro preenchidos: quatro datasets, cada não-signal atualizando só ao fechar candle próprio.
4. Em todos os casos, a fronteira da estratégia recebe apenas os datasets dos timeframes preenchidos.
5. Nenhum erro quando timeframes opcionais estão ausentes.
