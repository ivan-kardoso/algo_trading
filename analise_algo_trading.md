# Análise estrutural — `ivan-kardoso/algo_trading`

> Bot assíncrono de trading para **Binance USDM Futures**, multi-par, em arquitetura hexagonal com núcleo orientado por máquina de estados (FSM).
> Branch analisada: `main`. Documento gerado a partir do mapeamento incremental (ETAPAS 1–4).

---

## 1. Resumo executivo

O repositório contém **duas árvores paralelas**: `_legacy_reference/` (bot antigo, apenas referência, 37 arquivos `.py`) e `binance/usdm_futures/` (projeto ativo e raiz funcional, confirmada pelo mapeamento de pacote no `pyproject.toml`). Toda a análise abaixo trata do projeto **ativo**.

O sistema é um bot que opera vários pares simultaneamente sob `asyncio`. Cada par é descrito por um arquivo `.toml` próprio e roda como uma máquina de estados independente, com conexão e logger dedicados. A stack é enxuta: **ccxt** (acesso à exchange), **pydantic / pydantic-settings** (validação de config e segredos), **loguru** (logs) e **uv** como gerenciador (Python ≥ 3.14).

A arquitetura é madura e disciplinada nas fronteiras. O domínio (contratos, FSM, erros) não conhece `ccxt`; a decisão (transições puras) é separada do I/O (handlers); e toda a composição de dependências converge num único *composition root* (`app/bootstrap.py`). O ciclo de operação cobre janela de mercado, conexão, limpeza/normalização de posição, coleta de candles, estratégia, abertura de posição com proteção (SL obrigatório confirmado + TP best-effort), monitoramento e recuperação com retry limitado.

**Estado atual:** o pipeline está completo, mas a estratégia injetada é `NullStrategy` — um placeholder explícito que nunca emite sinal. Na prática, o bot roda até `CHECK_SIGNAL → STANDBY` indefinidamente. O "trilho" existe; falta a estratégia real (marcada como pendência no próprio código).

> **Nota:** esta é uma análise técnica/estrutural. Não avalia lucratividade, qualidade linha-a-linha, nem garante resultados financeiros.

---

## 2. Árvore de diretórios

```
algo_trading/
├── _legacy_reference/          # CÓDIGO ANTIGO — apenas referência (fora de escopo)
│   └── usdm_futures/           #   estrutura antiga (robot/ + shared/)
│
├── binance/                    # PROJETO ATIVO
│   ├── symbol_toml/
│   │   └── btcusdt.toml        #   config por símbolo (1 arquivo = 1 par)
│   ├── system_toml/
│   │   └── system_settings.toml#   config global do sistema
│   └── usdm_futures/           # ← RAIZ FUNCIONAL (pacote importável)
│       ├── app/
│       │   ├── main.py         #   entrypoint async multi-par
│       │   └── bootstrap.py    #   composition root (monta dependências)
│       ├── config/
│       │   ├── secrets.py      #   credenciais via .env (pydantic-settings)
│       │   ├── symbol_config.py#   modela/valida TOML do par
│       │   └── schedule.py     #   carrega SystemSettings globais
│       ├── domain/
│       │   ├── errors.py       #   hierarquia de exceções do robô
│       │   ├── models/         #   estratégias e timeframes válidos
│       │   ├── ports/          #   contratos hexagonais (I*Port) + tipos OHLCV
│       │   └── state_machine/  #   states.py (enums) + transitions.py (FSM pura)
│       ├── infrastructure/
│       │   ├── exchange_client.py  # adaptador ccxt (conexão + validações)
│       │   └── errors.py       #   tradução ccxt → erros de domínio
│       ├── market_data/
│       │   ├── source.py       #   fonte de candles (impl. do port)
│       │   ├── transform.py    #   validação de gaps de candles
│       │   └── memory_repository.py # dataset OHLCV em memória
│       ├── execution/
│       │   ├── order_utils.py  #   helpers de preço + parsing ccxt
│       │   ├── protection_orders.py # cria/confirma SL/TP
│       │   ├── position_tracker.py  # reconciliação de posição/proteção
│       │   └── order_executor.py    # execução de entrada + SL/TP
│       ├── strategy/
│       │   └── null_strategy.py     # placeholder (PENDÊNCIA)
│       ├── orchestration/
│       │   ├── symbol_runner.py     # motor da FSM (delega a handlers)
│       │   └── handlers/            # 1 handler por grupo de estados (×7)
│       ├── shared/
│       │   ├── helpers.py      #   renomeia TOML inválido
│       │   └── market_hours.py #   janela operacional semanal
│       └── logging/
│           └── logger.py       #   setup loguru + logger por par
│
├── main.py                     # shim placeholder na raiz (NÃO é o entrypoint real)
├── pyproject.toml / uv.lock    # dependências (uv + hatchling)
├── .python-version             # Python ≥ 3.14
├── .env.example                # template de segredos
├── BUILD_PLAN.md / CLAUDE.md / README.md   # documentação
└── executar_bot.txt            # instruções de execução
```

### Arquivos de configuração

| Arquivo | Papel |
|---|---|
| `pyproject.toml` | Projeto e dependências; mapeia o pacote para `binance/usdm_futures` |
| `uv.lock` | Lockfile do gerenciador uv |
| `.python-version` | Versão do Python fixada (≥ 3.14) |
| `.env.example` | Template de credenciais (prod/test) |
| `binance/system_toml/system_settings.toml` | Parâmetros globais (fetch, monitoring, execution, logging, market hours, timezone) |
| `binance/symbol_toml/btcusdt.toml` | Parâmetros por par (símbolo, timeframe, ordens, risco, sandbox) |

Não há `requirements.txt`, `setup.py`, `Dockerfile` nem testes automatizados — coerente com a filosofia de validação manual.

---

## 3. Padrão arquitetural

**Hexagonal (ports & adapters) + FSM com transições puras.** Três decisões definem o sistema:

1. **Domínio isolado de infraestrutura.** `domain/` define contratos (`I*Port`), tipos, erros e a FSM, e nunca importa `ccxt`. O conhecimento da exchange vive só nos adaptadores.
2. **Decisão separada do efeito colateral.** `transitions.py` tem funções puras `on_*(ctx, event)` que só decidem o próximo estado; `handlers/*` fazem todo o I/O e emitem eventos. O `SymbolRunner` costura os dois (`handler → transição`) por estado.
3. **Composition root explícito.** `app/bootstrap.py` é o único lugar que instancia classes concretas e injeta dependências; o resto depende só de interfaces.

Camadas, da mais interna para a mais externa:

```
domain (contratos, FSM, erros)              ← núcleo puro
   ↑  config · market_data · execution · strategy · infrastructure  ← adaptadores
   ↑  orchestration (symbol_runner + handlers)   ← motor da FSM
   ↑  app (bootstrap + main)                     ← composição e entrypoint
```

---

## 4. Fluxo de dados principal

**Inicialização (por par):** `app/main` carrega settings + secrets + logging, descobre os TOMLs, e para cada um `build_symbol_runner` carrega o `AssetSettings`, conecta o `ExchangeClient` (valida saldo e *One-way mode*), monta as cadeias de execução e dados, e devolve um `SymbolRunner`. Todos rodam sob `asyncio.gather`.

**Ciclo de operação (FSM, por par):**

```
CHECK_WINDOW → GET_PAIR → EXCHANGE → MANAGE_ORDERS → CLEAN_ORDERS_ORPHANS
                                                            │
                          ┌─────────────────────────────────┤
                          ▼ (sem posição)                    ▼ (com posição)
                     FETCH_DATA → APPLY_STRATEGY → CHECK_SIGNAL    MONITORING
                          │                             │              │ (fechou)
                          │                             ▼ (sinal)      │
                          │                       OPENING_POSITION ─────┤
                          └──────── STANDBY ◄───────────┘              ▼
                                                              CLEAN_ORDERS_ORPHANS
```

Candles entram via `OHLCVSource` (ccxt) → validados/dedup por `MemoryRepository` (janela deslizante em memória, sem persistência) → `apply_indicators` → `check_signal`. Um sinal grava `RunContext.signal_side` e dispara `OPENING_POSITION`: `OrderExecutor` envia a entrada e `ProtectionOrders` cria **SL obrigatório confirmado** (fecho de emergência se falhar) e **TP best-effort**. Depois fica em `MONITORING` até encerrar. `STANDBY` cobre esperas; `ERROR`/`STOPPED` cobrem recuperação com retry limitado.

---

## 5. Tabela-mestre (módulo · responsabilidade · depende de · usado por)

| Módulo | Responsabilidade | Depende de | Usado por |
|---|---|---|---|
| `domain/ports/*` (6) | Contratos hexagonais + tipos OHLCV | abc/typing | execution, market_data, strategy, orchestration |
| `domain/models/*` (2) | Estratégias/timeframes válidos | — | config/symbol_config |
| `domain/errors` | Hierarquia de exceções | — | infra, execution, market_data, orchestration |
| `domain/state_machine/states` | Enums `State`/`StandbyReason` | enum | transitions, orchestration |
| `domain/state_machine/transitions` | Transições puras + `RunContext` + eventos | dataclasses, enum, states | symbol_runner, handlers, bootstrap |
| `config/secrets` | Credenciais do `.env` | pydantic-settings | app/main, bootstrap |
| `config/symbol_config` | Valida TOML do par | domain/models, pydantic | bootstrap |
| `config/schedule` | `SystemSettings` globais | pydantic, zoneinfo | app/main, bootstrap, market_hours, orchestration, logger |
| `infrastructure/errors` | Tradução ccxt → domínio | ccxt, domain/errors | exchange_client, source, execution/* |
| `infrastructure/exchange_client` | Adaptador ccxt (conexão/validação) | ccxt, domain/errors | bootstrap, setup handler |
| `market_data/source` | Fonte de candles | ccxt, domain/ports | memory_repository, bootstrap |
| `market_data/transform` | Valida gaps de candles | domain/ports | memory_repository, bootstrap |
| `market_data/memory_repository` | Dataset OHLCV em memória | domain/*, transform | orchestration, bootstrap |
| `execution/order_utils` | Helpers de preço + parsing ccxt | decimal, ccxt | protection_orders, position_tracker, order_executor |
| `execution/protection_orders` | Cria/confirma SL/TP | ccxt, domain/ports, order_utils | position_tracker, order_executor, bootstrap |
| `execution/position_tracker` | Reconciliação de posição/proteção | ccxt, domain/ports, order_utils | orchestration, bootstrap |
| `execution/order_executor` | Execução de entrada + SL/TP | ccxt, domain/ports, order_utils | orchestration, bootstrap |
| `strategy/null_strategy` | Placeholder de estratégia (sem sinal) | domain/ports | bootstrap |
| `orchestration/symbol_runner` | Motor da FSM (delega a handlers) | config, domain/*, infra, shared, handlers | bootstrap, app/main |
| `orchestration/handlers/*` (7) | I/O de cada estado → emite evento | domain/*, infra, shared | symbol_runner |
| `shared/helpers` | Renomeia TOML inválido | pathlib | setup handler |
| `shared/market_hours` | Janela operacional semanal | zoneinfo, config/schedule | bootstrap, flow handler, symbol_runner |
| `logging/logger` | Setup loguru + logger por par | loguru, config/schedule | app/main, bootstrap |
| `app/bootstrap` | Composition root (monta tudo) | (todas as camadas) | app/main |
| `app/main` | Entrypoint async multi-par | config, logging, bootstrap | — (entrada) |

---

## 6. Riscos e débitos técnicos observados

Ordenados por relevância estrutural. Nenhum é bloqueante; a arquitetura macro é sólida e a dívida concentra-se na camada de execução e em fios soltos.

1. **Duplicação na camada de execução (mais relevante).** `PositionTracker` e `OrderExecutor` reimplementam, lado a lado, busca de posições, detecção de posição ativa, busca de ordens abertas (variantes regular + condicional) e cancelamento individual. Pior: a **semântica de erro diverge** — o tracker levanta exceção se ambas as variantes de busca falham (proteção contra recriação cega de SL/TP, "incidente C13"); o executor engole o erro (`except: pass`). Candidato a extrair um helper de acesso à exchange compartilhado, padronizando o tratamento de erro.

2. **Estratégia ausente (pendência conhecida).** O bot injeta `NullStrategy`, que nunca emite sinal; o fluxo real estaciona em `STANDBY`. Há também um descompasso entre `VALID_STRATEGIES = {"triple-ema"}` (o que o TOML é obrigado a declarar) e a implementação real (inexistente). Intencional e documentado, mas é a maior lacuna funcional.

3. **Verificação de permissão de API key é código morto.** `_check_api_permissions` (bloquear key com saque, exigir leitura/futures) está implementado mas **nunca é chamado** por `connect()`. A defesa existe mas não está ligada; a exceção `ApiPermissionError` nunca é levantada.

4. **`open_order` longo e complexo (~130 linhas).** Vários ramos de reconciliação (ordem sem id; `filled=0` mas posição existe). Alta complexidade ciclomática, difícil de validar manualmente. Candidato a decomposição. O retorno é um `dict` solto (`success`, `order`, `entry_price`...) em vez de um modelo tipado.

5. **Inconsistência na hierarquia de erros.** `HedgeModeError` e `ApiPermissionError` foram criados no domínio, mas os bloqueios correspondentes acontecem via `return False` + log, não via exceção. A hierarquia de erros está parcialmente subutilizada.

6. **Nomes que subdimensionam responsabilidades.** `config/schedule.py` carrega o `SystemSettings` inteiro (não só "schedule") e é um nó de dependência largo. `market_data/transform.py` só valida gaps, não transforma.

7. **Estado global no `logging/logger.py`.** Variáveis de módulo (`_log_dir`, `_config`, `_registered_pairs`) criam um contrato de ordem implícito (`setup_logging` antes de `get_pair_logger`). Respeitado hoje, mas frágil.

8. **Ausência de testes automatizados.** As transições da FSM são funções puras — projetadas para serem testáveis sem mocks — mas não há nenhum teste. Coerente com a filosofia de validação manual via notebooks, porém arriscado dado o número de ramos de estado e retry.

9. **Detalhes menores.** Em `handlers/execution.py`, o log condicional `if entry_price` trataria `0.0` como ausente (irrelevante na prática). O `main.py` da raiz é um placeholder que pode confundir sobre qual é o entrypoint real (`app/main.py`).

### Pontos fortes a preservar numa reconstrução

- Separação domínio ↔ infraestrutura via ports.
- Transições puras isoladas dos handlers (testável, previsível).
- Composition root único e explícito.
- Semântica de risco cuidadosa: SL obrigatório e confirmado, TP best-effort, margem ISOLATED, *One-way mode* validado, nunca fecha posição automaticamente na normalização.
- Coleta de dados idempotente (dedup por timestamp + janela deslizante em memória).
