# Handoff — Reconstrução do bot `algo_trading`

> **Propósito deste documento.** Consolidar o contexto que existe apenas na conversa de depuração/desenvolvimento e que **não** está capturado em nenhum arquivo do repositório. Serve como ponto de partida para o chat novo dedicado à reconstrução.
>
> **Este documento NÃO repete a arquitetura.** A descrição completa do projeto atual (árvore de diretórios, tabela-mestre, fluxo de dados, arquitetura, riscos) está em **`analise_algo_trading.md`**, já commitado no repositório. Leia aquele documento primeiro; este aqui cobre o que aquele não cobre.

---

## 0. Contexto da tarefa

**Objetivo:** reconstruir o bot do zero, **sem tocar no projeto atual** (que fica funcionando como referência).

**Método definido pelo Ivan:**
- Digitar o código **linha a linha** (sem copiar e colar), para compreensão total do funcionamento.
- Aproveitar a reconstrução para **corrigir os débitos técnicos** conhecidos.
- Incluir **novas funcionalidades** — a definir conforme o projeto cresce (Ivan optou por não pré-registrá-las; serão decididas ao longo do caminho).

**Referências disponíveis para o chat de reconstrução:**
- `analise_algo_trading.md` — mapa arquitetural completo do projeto atual (no repo).
- Repositório `ivan-kardoso/algo_trading` — referência viva; pode ser clonado e lido.
- Skill `binance-usdm-futures-rebuild-guide` — guia de reconstrução incremental.

> **Escopo — IGNORAR a pasta `_legacy_reference/`.** O repositório contém `_legacy_reference/` (o bot ANTIGO, ~37 arquivos `.py`). Ela é **histórico obsoleto** e deve ser **desconsiderada por padrão** — não ler, não citar, não usar como base, salvo pedido explícito do Ivan. A arquitetura nova (em `binance/usdm_futures/`) foi desenhada justamente para superar aquela estrutura, e parte da dívida técnica atual foi *herdada* do legado (ex.: o `max_rows` órfão — ver seção 2). Toda a reconstrução parte de `binance/usdm_futures/` como referência, nunca do legado.

---

## 1. Bugs já resolvidos no projeto atual (não reintroduzir)

Estes foram descobertos e corrigidos durante os testes de testnet. Na reconstrução, evitar reintroduzi-los:

1. **`RunContext.has_symbol` nunca era setado.** O bootstrap carregava o símbolo mas não ligava a flag `has_symbol`, fazendo o estado `GET_PAIR` cair direto em `ERROR` (3 retries → encerra), sem logar nada. Correção: `has_symbol=True` na construção do `RunContext`. **Lição de desenho:** o ramo `GET_PAIR → ERROR` não loga nada — um erro "que nunca deveria ocorrer" precisa gritar quando ocorre.

2. **`max_rows = 3` truncava o dataset.** Em `system_settings.toml`, `[fetch] max_rows = 3` cortava o dataset para os últimos 3 candles no `_merge_and_trim`, mesmo com `candle_limit = 150`. `max_rows` é o teto da janela deslizante; `candle_limit` é a carga inicial. Regra: **`max_rows >= candle_limit`** sempre. Corrigido para `max_rows = 200`. **Não há validação cruzada** que impeça `max_rows < candle_limit` (os dois parâmetros vivem em arquivos diferentes) — candidato a validação na reconstrução.

3. **Import inconsistente em `strategy_config.py`.** Havia um `from usdm_futures.domain...` (absoluto, pacote inexistente) misturado com imports relativos. O pacote raiz é `binance.usdm_futures`. Corrigido para relativo (`from ..domain...`). **Lição:** padronizar todos os imports como relativos.

---

## 2. Débitos técnicos acumulados (além dos que já constam no `analise_algo_trading.md`)

O `analise_algo_trading.md` já lista 9 débitos (duplicação `PositionTracker`/`OrderExecutor`, `_check_api_permissions` morto, `open_order` complexo, erros criados mas nunca levantados, nomes que subdimensionam, estado global no logger, ausência de testes, etc.). **Consultar aquela seção.** Os itens abaixo foram levantados na conversa e complementam aquela lista:

1. **Papel do `max_rows` é incerto.** Foi herdado do projeto legado; origem e propósito original não lembrados. A definir se ainda faz sentido na arquitetura nova, onde o dataset é uma janela deslizante alimentada por `candle_limit` inicial + `_download_incremental`. Possível redundância/sobreposição de papel com `candle_limit`. **Revisar na reconstrução.**

2. **Padronizar os nomes dos loaders de config.** Hoje irregular: `symbol_config.py` e `strategy_config.py` usam sufixo `_config`; mas `schedule.py` (carrega `SystemSettings`) e `secrets.py` não seguem convenção. Alinhar num padrão único.

3. **Falta validação cruzada `max_rows >= candle_limit`.** Ver bug #2 da seção anterior. Como moram em arquivos diferentes (`system_settings.toml` global vs. TOML do par), é fácil reintroduzir o desencontro. Considerar validação na inicialização.

4. **Contrato `apply_indicators` vs. estratégia sem estado.** O port `IStrategyPort.apply_indicators(data) -> OHLCVData` pressupõe que o método *anexa* indicadores ao dataset. A `TripleEmaStrategy` foi desenhada sem estado (recalcula no `check_signal`), o que torna `apply_indicators` um no-op. Revisar se o contrato do port faz sentido no desenho novo, ou se deve ser repensado.

---

## 3. Estratégia `triple-ema` — decisões de desenho

Todas as decisões abaixo foram tomadas em conjunto e valem para a reconstrução. O indicador EMA e a classe da estratégia já existem no projeto atual como referência.

### 3.1 Arquitetura da estratégia
- **Indicadores em pasta dedicada e pura:** `usdm_futures/indicators/` (na raiz, fora de `strategy/`). Cada indicador é um módulo próprio (`ema.py`, etc.), operando sobre **listas de floats crus** (não sobre `OHLCVData`). Quem extrai a coluna do OHLCV é a estratégia.
- **Estratégia sem estado.** Não guarda memória entre chamadas. O `check_signal` **reconstrói** o estado do gatilho varrendo o dataset a cada chamada. Motivos: coerência com transições puras da FSM, robustez a reinícios (estado derivado dos candles reais), testabilidade.
- **Config da estratégia em arquivo próprio:** `binance/strategy_toml/<strategy>.toml` (pasta irmã de `symbol_toml/`). O nome do arquivo **casa exatamente** com o valor de `strategy` no TOML do par (ex.: `strategy = "triple-ema"` → `triple-ema.toml`, com hífen). O bootstrap deriva o caminho por concatenação direta, sem mapa nem conversão.
- **EMA cálculo:** semente por SMA dos primeiros `period` valores, depois `EMA = (preço − EMA_ant)·k + EMA_ant`, `k = 2/(period+1)`. Saída alinhada por índice ao dataset (primeiros `period−1` valores são `None`). Levanta `ValueError` se `len(data) < period`.
- **Períodos (do `triple-ema.toml`):** fast=25, medium=50, slow=100. O `slow_period=100` define o mínimo de candles; com `candle_limit=150` há folga.

### 3.2 Regras de sinal — COMPRA
1. **Alinhamento (obrigatório), no último candle:** `ema_fast > ema_medium > ema_slow` (tendência de alta).
2. **Veio de cima:** o candle **imediatamente anterior** fechou **acima** da EMA rápida.
3. **Gatilho (pullback):** o candle atual fecha `<= EMA rápida` **OU** `<= EMA média`. Arma o gatilho.
4. **Sinal:** com o gatilho armado, um candle fecha **acima** da EMA rápida → **compra a mercado**.
5. **Tempo de vida / desarme:** após armado, o gatilho vale até que um candle feche **abaixo da EMA lenta**. Se isso ocorrer, o gatilho é **zerado** e o sistema fica livre para um novo gatilho (compra OU venda). Razão: fechar abaixo da lenta é região de indecisão/possível inversão — por precaução, zera-se o gatilho.

### 3.3 Regras de sinal — VENDA (espelhado)
1. Alinhamento: `ema_fast < ema_medium < ema_slow` (tendência de baixa).
2. Veio de baixo: candle anterior fechou **abaixo** da EMA rápida.
3. Gatilho: candle atual fecha `>= EMA rápida` **OU** `>= EMA média`.
4. Sinal: com gatilho armado, candle fecha **abaixo** da EMA rápida → **venda a mercado**.
5. Desarme: gatilho vale até um candle fechar **acima da EMA lenta** → zera, libera novo gatilho.

### 3.4 Decisões de implementação (validar nos testes)
- **Sinal só dispara no último candle.** Se o gatilho armou e disparou num candle antigo (meio do dataset), isso é passado — consome-se o gatilho e segue. `check_signal` só retorna `buy`/`sell` se o disparo acontece no candle mais recente. Alinhado com a FSM chamar `check_signal` a cada novo candle.
- **Ordem de avaliação por candle: desarme → disparo → armação.** Desarme precede tudo (mais conservador). Um candle não arma e dispara no mesmo passo.
- **Varredura vai até o início do dataset.** Horizonte máximo do gatilho = tamanho da janela (`max_rows`, hoje 200). Em candle de 15m, um gatilho pode ter armado ~100 candles atrás, então varrer tudo é intencional. Limite natural: gatilho armado há mais de `max_rows` candles sem desarmar/disparar "sai" da memória.
- **Candles iniciais com EMA `None`** (antes da lenta aquecer) são pulados na varredura.

---

## 4. Roteiro de testes da estratégia (para a fase de indicadores/estratégia da reconstrução)

Testes com **dados fictícios** simulando inconsistências e comportamentos indesejados. **Não executar antes da reconstrução** — reservados para quando o chat novo chegar à camada de indicadores/estratégia.

1. **Sinal só no último candle** — gatilho que arma e dispara no meio do dataset NÃO gera sinal; só disparo no candle mais recente retorna `buy`/`sell`.
2. **Ordem por candle (desarme→disparo→armação)** — candle que poderia desarmar e disparar ao mesmo tempo: desarme vence.
3. **Reconstrução por varredura** — estado do gatilho reconstruído bate com o esperado; caso-limite do gatilho que "sai" da janela `max_rows`.
4. **Candles iniciais com EMA `None`** — primeiros candles (antes da EMA de 100 aquecer) são pulados sem gerar falsos gatilhos nem quebrar a varredura.
5. **Simetria compra/venda** — regras espelhadas produzem sinais equivalentes em cenários invertidos.
6. **Transições de estado indesejadas** — gatilho arma, não dispara, desarma corretamente; sistema livre após desarme; nenhum sinal preso ou gatilho fantasma.
7. **Fronteiras dos operadores** — gatilho usa `<=`/`>=` (rápida/média); desarme usa `<`/`>` estrito (lenta). Testar valores exatamente iguais às EMAs para confirmar o operador certo.

---

## 5. Método de trabalho da reconstrução

**Não é "digitar tudo e depois ligar as peças".** É construção incremental com validação a cada passo: escrever um método → testá-lo isolado → entender seu comportamento → só então ligar na próxima peça. Montar de baixo para cima, verificando cada tijolo antes de assentar o próximo. O objetivo do Ivan é entender como cada peça se encaixa e se comporta dentro do sistema, não só produzir código.

**Política de testes:**
- **Testnet é o ambiente de validação primário.** É para isso que ela existe. Sempre que uma peça puder ser exercitada contra a testnet, testar contra a testnet.
- **Dados fabricados são exceção** — só quando a testnet não consegue produzir o cenário. Caso típico: forçar condições específicas de sinal na estratégia (os 7 testes da seção 4), onde não dá para esperar o mercado gerar a condição exata. Lógica pura (indicadores, transições da FSM, `check_signal`) valida-se com entradas fabricadas + conferência de saída.

**Ordem de fundação (consequência de testar na testnet):**
Como a validação é contra a testnet, o **módulo de conexão é fundação, não peça tardia** — sem conexão não há como testar quase nada contra a testnet. As fundações são, portanto:
1. **Configuração do sistema** (`SystemSettings`) e **configuração do par** (`AssetSettings`) — a conexão depende delas (credenciais, sandbox, símbolo).
2. **Segredos** (`Secrets`) — credenciais do `.env`.
3. **Módulo de conexão** (`ExchangeClient`) — o alicerce sobre o qual o resto é validado na testnet.

A partir dessas fundações, as demais camadas vão sendo construídas e ligadas incrementalmente, cada uma testada contra a testnet assim que possível (dados de mercado, execução, estratégia, orquestração). Nota: esta ordem de *construção* (de dentro para fora, do que é fundação para o que depende dela) é diferente da ordem de *leitura* usada no mapeamento do `analise_algo_trading.md` (de fora para dentro, dos contratos para as implementações).

---

## 6. Estado atual do projeto de referência (marco atingido)

No momento deste handoff, o projeto atual (referência) está com:
- Pipeline rodando de ponta a ponta no **testnet**.
- Estratégia `triple-ema` **ativa e fiada no bootstrap** (substituiu o `NullStrategy`), ciclando corretamente em `STANDBY` a cada candle sem sinal.
- **Ainda não exercitado no testnet:** todo o caminho de execução `OPENING_POSITION → ordem → SL/TP → MONITORING`. Ele só roda quando um sinal dispara de fato. É a parte mais endividada do código (ver duplicação `PositionTracker`/`OrderExecutor` no `analise`) e o próximo ponto de atenção nos testes.

**Working style do Ivan (para o chat de reconstrução):** deliberado e incremental. Entende profundamente antes de mudar. Prefere uma micro-tarefa por vez, uma pergunta por vez, sem muros de texto. Confirma antes de avançar. Digita o código à mão (respostas com código devem ser claras e do tamanho certo para transcrição).
