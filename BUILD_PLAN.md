# BUILD_PLAN.md — Plano de Reconstrução Incremental

Plano de fases para reconstruir o robô do início ao fim, de ponta a ponta e
funcional, **exceto** a lógica de estratégia/indicadores (pendência final). Cada
fase só deve começar após a confirmação explícita do usuário sobre a fase
anterior. Nenhuma fase contém código — apenas descrição e critérios.

---

### Fase 0 — Esqueleto do pacote

- **Objetivo:** criar a árvore de pastas completa sob `binance/usdm_futures/`,
  com arquivos vazios/stubs, sem nenhuma lógica.
- **Módulos/pastas:** todos os listados no `CLAUDE.md`.
- **Critério de conclusão:** estrutura existe, é importável, sem ciclos de
  importação.
- **Dependência:** nenhuma (fase inicial).

### Fase 1 — Configuração e segredos

- **Objetivo:** `config/secrets.py`, `config/schedule.py` e
  `config/symbol_config.py` já estão implementados pelo usuário — esta fase
  não é de implementação, e sim de **avaliação de alinhamento** com o
  `CLAUDE.md` (convenções, proibição de libs, responsabilidade única) e
  ajustes pontuais, se houver.
- **Módulos/pastas:** `config/secrets.py`, `config/schedule.py`,
  `config/symbol_config.py`.
- **Critério de conclusão:** os três módulos foram revisados quanto ao
  alinhamento com o `CLAUDE.md`; ajustes necessários (se houver) foram
  listados e aplicados; configurações continuam carregando e validando
  corretamente a partir de um `.env` e um `.toml` de exemplo (sem credenciais
  reais).
- **Dependência:** Fase 0.

### Fase 2 — Logging

- **Objetivo:** configurar logging central com `loguru`, substituindo `rich`.
- **Módulos/pastas:** `logging/logger.py`.
- **Critério de conclusão:** logger emite mensagens formatadas em console e
  arquivo de teste, sem qualquer dependência de `rich`.
- **Dependência:** Fase 0.

### Fase 3 — Erros de domínio

- **Objetivo:** portar a hierarquia de exceções de domínio do legado (erros de
  autenticação, rate limit, posição não encontrada, OHLCV vazio etc.).
- **Módulos/pastas:** `domain/errors.py`.
- **Critério de conclusão:** hierarquia cobre os mesmos tipos de erro do
  legado, sem depender de `ccxt` neste módulo.
- **Dependência:** Fase 0.

### Fase 4 — Cliente de exchange (infraestrutura)

- **Objetivo:** portar o client assíncrono CCXT — criação de instância,
  validação de conexão, modos sandbox/produção, fechamento de sessão — e a
  tradução de exceções `ccxt` para exceções de domínio.
- **Módulos/pastas:** `infrastructure/exchange_client.py`,
  `infrastructure/errors.py`.
- **Critério de conclusão:** conexão de teste em modo sandbox é validada
  manualmente (sem ordens reais).
- **Dependência:** Fases 1, 3.

### Fase 5 — Portas de domínio (abstrações)

- **Objetivo:** definir as interfaces que desacoplam orquestração e execução
  da infraestrutura concreta (exchange, ordens, dados de mercado, estratégia).
- **Módulos/pastas:** `domain/ports/`.
- **Critério de conclusão:** contratos cobrem todos os métodos que
  `execution/`, `market_data/` e `strategy/` precisarão expor.
- **Dependência:** Fase 4.

### Fase 6 — Dados de mercado em memória

- **Objetivo:** portar a coleta e normalização de candles, sem `pandas` e sem
  persistência em disco — dataset mantido em memória durante o ciclo de vida
  do robô.
- **Módulos/pastas:** `market_data/source.py`, `market_data/transform.py`,
  `market_data/memory_repository.py`.
- **Critério de conclusão:** dataset OHLCV é obtido, validado e mantido em
  memória para um símbolo de teste, sem nenhum arquivo gravado em disco.
- **Dependência:** Fases 4, 5.

### Fase 7 — Execução de ordens

- **Objetivo:** portar envio/cancelamento de ordens, normalização de posição e
  ordens de proteção (stop loss / take profit), divididos por responsabilidade.
- **Módulos/pastas:** `execution/order_executor.py`,
  `execution/position_tracker.py`, `execution/protection_orders.py`.
- **Critério de conclusão:** operações validadas manualmente em modo sandbox
  (sem ordens reais).
- **Dependência:** Fases 4, 5.

### Fase 8 — Máquina de estados (núcleo) — FASE CRÍTICA

- **Objetivo:** migrar os estados e transições do `StateChief` legado
  **preservando o comportamento** (mesmos estados, mesmas condições de
  transição, mesmos critérios de retry/erro), isolando a definição da FSM de
  execução, conexão externa e estratégia.
- **Módulos/pastas:** `domain/state_machine/states.py`,
  `domain/state_machine/transitions.py`.
- **Critério de conclusão:** todos os estados do legado (`CHECK_WINDOW`,
  `GET_PAIR`, `EXCHANGE`, `MANAGE_ORDERS`, `CLEAN_ORDERS_ORPHANS`,
  `FETCH_DATA`, `APPLY_STRATEGY`, `CHECK_SIGNAL`, `OPENING_POSITION`,
  `MONITORING`, `STANDBY`, `ERROR`, `STOPPED`) estão mapeados 1:1, com as
  mesmas regras de transição documentadas e revisáveis sem depender de
  infraestrutura.
- **Dependência:** Fase 5.

### Fase 9 — Motor de orquestração por par

- **Objetivo:** portar o "motor" que executa a FSM por símbolo, delegando cada
  estado a um handler que usa apenas as `domain/ports/` (sem acoplamento direto
  a execução ou conexão).
- **Módulos/pastas:** `orchestration/symbol_runner.py`,
  `orchestration/handlers/`.
- **Critério de conclusão:** o runner percorre o ciclo completo de um par
  (sem sinal real de estratégia ainda) usando handlers e ports, com logging e
  retries equivalentes ao legado.
- **Dependência:** Fases 6, 7, 8.

### Fase 10 — Interface reservada de estratégia (pendência)

- **Objetivo:** criar apenas o ponto de extensão vazio para estratégia e
  indicadores, sem nenhuma lógica de decisão.
- **Módulos/pastas:** `strategy/`.
- **Critério de conclusão:** módulo existe e é importável pelo orquestrador,
  mas não contém lógica de sinal; documentado como pendência.
- **Dependência:** Fase 5.

### Fase 11 — Composição e execução multipar

- **Objetivo:** montar o composition root e o ponto de entrada que orquestra
  múltiplos `symbol_runner` concorrentemente via `asyncio`.
- **Módulos/pastas:** `app/bootstrap.py`, `app/main.py`.
- **Critério de conclusão:** dois ou mais pares de teste rodam
  concorrentemente em modo sandbox, sem bloqueio mútuo entre eles.
- **Dependência:** Fases 9, 10.

### Fase 12 — Validação ponta a ponta

- **Objetivo:** validar o robô completo — assíncrono, multipar, do início ao
  fim — em ambiente sandbox, sem lógica de estratégia real (sinal neutro/placeholder).
- **Módulos/pastas:** todos.
- **Critério de conclusão:** ciclo completo roda sem erros para múltiplos
  pares simultâneos em sandbox.
- **Dependência:** todas as fases anteriores.

---

## Estado final

Ao final da Fase 12, o robô está completo e funcional de ponta a ponta —
assíncrono, multipar, com máquina de estados preservada e reorganizada — com
**uma única pendência**: o módulo `strategy/` permanece apenas como estrutura
e interface reservada, sem lógica de estratégia ou indicadores. Essa
implementação deverá ser feita posteriormente, em outra conversa, com apoio
do chat.
