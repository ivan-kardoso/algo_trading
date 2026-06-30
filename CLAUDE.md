# CLAUDE.md — Robô Multipar USDM Futures (Binance)

## Visão geral

Robô de trading assíncrono para futuros perpétuos USDT (USDM Futures) na Binance,
capaz de operar **múltiplos pares simultaneamente**. Cada par é gerenciado por uma
máquina de estados independente, orquestrada de forma concorrente via `asyncio`.

Esta é uma reconstrução do zero do projeto legado, focada em separação de
responsabilidades, baixo acoplamento e testabilidade. A lógica de estratégia e
indicadores **não** faz parte desta reconstrução (ver seção *Pendências*).

## Módulos já implementados

Os três módulos de `config/` já existem no projeto novo, escritos previamente
pelo usuário:

- `config/secrets.py` — leitura do `.env`.
- `config/schedule.py` — configurações gerais de sistema/janela operacional.
- `config/symbol_config.py` — leitura do arquivo de configuração do par
  (TOML).

Para esses três módulos, o papel do Claude Code **não é reescrever do zero**,
e sim avaliar alinhamento com este documento (convenções, proibição de libs,
responsabilidade única) e propor apenas os ajustes necessários, se houver.
Demais módulos da árvore abaixo ainda não existem e seguem o `BUILD_PLAN.md`
normalmente.

## Referência ao projeto legado

O projeto antigo está disponível em `_legacy_reference/`, **fora** da raiz
lógica `binance/usdm_futures/`. Trata-se de material de consulta, não de
código a ser reaproveitado.

- `_legacy_reference/` é somente leitura: nunca editar, apagar ou gravar
  arquivos ali.
- Nunca importar, copiar literalmente ou referenciar `_legacy_reference/` a
  partir de código em `binance/usdm_futures/` — toda a implementação nova
  vive exclusivamente dentro da raiz lógica.
- Uso permitido: consultar `_legacy_reference/` para comparar comportamento,
  principalmente da máquina de estados (Fase 8 do `BUILD_PLAN.md`), e
  entender regras de negócio existentes antes de reorganizar um módulo.
- Em caso de dúvida sobre se um arquivo pertence ao projeto novo ou é
  apenas referência, o caminho decide: `binance/usdm_futures/` é o único
  destino de código novo.

## Estrutura de pastas

Raiz lógica do projeto: `binance/usdm_futures/`

```
binance/
└── usdm_futures/
    ├── app/
    │   ├── main.py              # ponto de entrada assíncrono; lê os TOMLs dos pares e inicia a execução multipar
    │   └── bootstrap.py         # composition root: monta e injeta as dependências concretas nos runners (sem regra de negócio)
    │
    ├── domain/                  # núcleo de negócio — sem dependência de bibliotecas externas
    │   ├── state_machine/
    │   │   ├── states.py        # Enums State e StandbyReason (preservados do legado)
    │   │   └── transitions.py   # regras puras de transição entre estados (sem I/O, sem side effects)
    │   ├── models/               # objetos de domínio (config de símbolo, sinal, posição aberta, contexto de monitoramento)
    │   ├── ports/                 # interfaces que desacoplam orquestração de infraestrutura (exchange, ordens, dados, estratégia)
    │   └── errors.py               # hierarquia de exceções de domínio (sem dependência de ccxt)
    │
    ├── orchestration/             # motor que executa a máquina de estados por par
    │   ├── symbol_runner.py        # reorganização do StateChief legado: percorre estados e delega aos handlers via ports
    │   └── handlers/                # um módulo por estado (ou grupo coeso de estados), dependendo apenas das ports
    │
    ├── execution/                  # execução de ordens na exchange
    │   ├── order_executor.py        # envio e cancelamento de ordens
    │   ├── position_tracker.py      # consulta e normalização do estado da posição
    │   └── protection_orders.py     # criação/recriação de ordens de stop loss e take profit
    │
    ├── market_data/                 # coleta e preparo dos dados de mercado
    │   ├── source.py                  # busca de candles na exchange
    │   ├── transform.py               # validação e normalização dos candles
    │   └── memory_repository.py       # armazenamento do dataset OHLCV em memória (sem CSV/disco)
    │
    ├── strategy/                      # PENDÊNCIA — reservado para estratégia e indicadores (vazio, ver Pendências)
    │
    ├── infrastructure/                 # adaptadores concretos para serviços externos
    │   ├── exchange_client.py           # client assíncrono CCXT (conexão, autenticação, sandbox/produção)
    │   └── errors.py                     # tradução de exceções da exchange (ccxt) para exceções de domínio
    │
    ├── config/                          # carregamento e validação de configuração
    │   ├── secrets.py                     # variáveis sensíveis via .env (chaves de API)
    │   ├── schedule.py                     # janela operacional de mercado
    │   └── symbol_config.py                 # configuração por par via TOML
    │
    ├── logging/
    │   └── logger.py                      # configuração central de logging com loguru
    │
    └── shared/                            # utilitários puros, sem dependência de infraestrutura
        ├── helpers.py                       # formatação de símbolo, marcação de TOML usado/inválido
        └── market_hours.py                   # cálculo de janela de mercado (depende só de config)
```

A árvore é intencionalmente enxuta: cada pasta representa uma responsabilidade,
sem subníveis desnecessários.

## Máquina de estados

Local conceitual: `domain/state_machine/`.

Os estados e transições do `StateChief` legado devem ser **preservados em
comportamento** — mesmos estados, mesmas condições de transição, mesmos critérios
de retry/erro — porém reorganizados: o módulo `domain/state_machine/` contém apenas
a definição dos estados e o grafo/regras de transição, sem conhecer execução de
ordens, conexão com a exchange ou estratégia. Quem executa efetivamente cada estado
(I/O, chamadas externas, side effects) é o `orchestration/symbol_runner.py`, que
depende apenas das `domain/ports/`.

## Estratégia e indicadores (pendência)

Local conceitual: `strategy/`. Pasta reservada e vazia nesta reconstrução — sem
lógica, sem regras, sem indicadores. Ver seção *Pendências*.

## Convenções adotadas

- SOLID e Clean Code, com ênfase em Responsabilidade Única por módulo/classe.
- Programação assíncrona (`asyncio`) em toda a base do projeto.
- Logging via `loguru` (substitui o uso de `rich` do legado).
- Proibido introduzir, em qualquer fase: `pandas`, `pandas-ta-classic`, `aiohttp`,
  `requests`, `rich`.
- Dados OHLCV mantidos **apenas em memória** durante o ciclo de vida do robô — sem
  persistência em disco (sem CSV, sem banco de dados).
- Segredos/credenciais ficam em `.env`; configurações gerais ficam em `.toml`
  (configuração por par) — sem conteúdo desses arquivos definido nesta etapa.
- Módulos de orquestração e execução dependem de abstrações (`domain/ports/`), não
  diretamente de `ccxt` ou de outras bibliotecas externas.

## Requisitos obrigatórios

- A máquina de estados deve manter o mesmo conjunto de estados e transições do
  projeto legado, apenas reorganizada estruturalmente.
- O robô deve operar **múltiplos pares simultaneamente**, cada um com seu próprio
  `symbol_runner`, orquestrados de forma concorrente em `app/main.py`.
- Toda a base deve permanecer assíncrona, do ponto de entrada à execução de ordens.

## Regras de escopo (válidas em toda a reconstrução)

- Não operar conta real, não enviar ordens reais, não configurar credenciais reais.
- Não introduzir `pandas`, `pandas-ta-classic`, `aiohttp`, `requests` ou `rich` em
  nenhuma fase.
- Não persistir OHLCV em disco em nenhuma fase.
- Não implementar lógica de estratégia, indicadores, sinais ou regras de decisão.
- Não avançar para a próxima fase do `BUILD_PLAN.md` sem confirmação explícita.

## Pendências

O módulo `strategy/` (estratégia + indicadores) **não deve ser implementado** nesta
reconstrução. Deve permanecer apenas como pasta/interface reservada e vazia. A
implementação da lógica de estratégia e indicadores ficará para uma etapa
posterior, em outra conversa, com apoio do chat.
