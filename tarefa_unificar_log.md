# Tarefa: unificar o log em um único arquivo por par

## Contexto

Este bot roda **um único par por execução** — cada par é executado isoladamente, em sua própria sessão/processo. Nunca há mais de um par na mesma execução.

Hoje o sistema grava **dois arquivos de log com conteúdo praticamente duplicado**:

- `bot.log` — sink geral, sem filtro, que captura todos os eventos.
- `{par}.log` (ex.: `btcusdt.log`) — sink filtrado por `extra["pair"]`, que captura só os eventos daquele par.

Como as duas gravações capturam quase o mesmo conteúdo, há duplicação indesejada.

## Objetivo

Eliminar a duplicação e passar a gravar **apenas um arquivo de log por execução**, nomeado com o par em questão, contendo **todos** os eventos daquela execução (sem exceção).

## Arquivo principal a alterar

`binance/usdm_futures/logging/logger.py`

Estrutura atual relevante:
- `setup_logging(config, log_dir)` — registra o sink de console (`sys.stderr`) e o sink do arquivo geral `bot.log` (sem filtro).
- `get_pair_logger(symbol)` — registra, uma vez por par, um sink de arquivo `{clean}.log` com filtro `record["extra"].get("pair") == clean`, e retorna `logger.bind(pair=clean)`.

## Requisitos

1. **Remover o sink do `bot.log`** em `setup_logging`. Não deve mais existir um arquivo geral.

2. **Manter um único arquivo por par** (`{clean}.log` em `get_pair_logger`) e **manter o sink de console** (`sys.stderr`) — sem alterar formato, rotação (`log_max_bytes`) nem retenção (`log_backup_count`).

3. **Garantir que TODOS os eventos sejam gravados no arquivo do par**, inclusive os eventos gerais emitidos sem `pair` associado (por exemplo, os logs de `app/main.py`: "Bot USDM Futures iniciado", "N arquivo(s) de par encontrado(s)", "Iniciando execução concorrente", "Fechando conexões", "Bot encerrado"). Hoje o filtro do sink por par (`record["extra"].get("pair") == clean`) **exclui** eventos sem `pair`, então eles não entram no arquivo do par. Ajuste para que eventos sem `pair` também sejam gravados no arquivo do par. Como só há um par por execução, todos os eventos pertencem à mesma execução e devem ir para o mesmo arquivo.

   Abordagem sugerida (avaliar a melhor): alterar o filtro do sink do par para aceitar registros cujo `extra["pair"]` seja igual ao par **ou** ausente/nulo. Alternativamente, fazer os logs gerais usarem o logger vinculado ao par. Escolher a solução que garanta que nenhum evento fique de fora do arquivo do par, sem quebrar o cenário de execução isolada por par.

4. **Verificar dependências do `bot.log`**: procurar em todo o código (fora do `logger.py`) qualquer referência ou dependência do arquivo `bot.log` e ajustar/remover conforme necessário.

5. **Validação final**: confirmar que uma execução de um par gera **exatamente um** arquivo de log (`{par}.log`) contendo todos os eventos daquela execução — inclusive os eventos gerais de início/fim — e que o console continua exibindo tudo normalmente.

## Restrições

- Não alterar o **formato** das mensagens de log (`_CONSOLE_FORMAT` e `_FILE_FORMAT`).
- Não alterar a **rotação** nem a **retenção** dos arquivos.
- Alterar apenas a **estrutura de quais arquivos são criados** e o **roteamento dos eventos** para o arquivo do par.
