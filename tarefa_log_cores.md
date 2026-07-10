# Tarefa: cores sóbrias no log via níveis customizados do loguru

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR `binance/usdm_futures/strategy/triple_ema.py`.** Ignore-o completamente.

## Objetivo

Aplicar cores sóbrias ao log do console, usando **níveis customizados do loguru** definidos centralmente em `binance/usdm_futures/logging/logger.py`. Rotina fica apagada (cinza); datasets e posições ganham cor.

## Paleta (usar exatamente estas cores loguru)

- **Rotina** (todos os `logger.info` comuns): cinza apagado → `<dim>`
- **Atualização de datasets**: ciano suave → `<dim><cyan>`
- **Abertura de posição**: verde forte → `<green><bold>`
- **Fechamento de posição**: magenta forte → `<magenta><bold>`
- **ERROR/WARNING**: não mexer, manter o padrão do loguru.

(O alinhamento de médias NÃO faz parte desta tarefa — ignore-o.)

## Implementação

### 1. Definir níveis customizados em `setup_logging` (logger.py)

Registrar três níveis novos, com `no` entre INFO(20) e WARNING(30):

```python
logger.level("DATASET", no=22, color="<dim><cyan>")
logger.level("POS_OPEN", no=23, color="<green><bold>")
logger.level("POS_CLOSE", no=24, color="<magenta><bold>")
```

### 2. Colorir a MENSAGEM inteira pelo nível

Hoje `_CONSOLE_FORMAT` é:
```
<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}
```
Ajustar para que a **mensagem** seja colorida pelo nível, envolvendo `{message}` com `<level>...</level>`:
```
<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>
```
Assim a linha inteira assume a cor do nível. Para os `info` comuns (rotina), a cor deve ser o cinza apagado `<dim>` — para isso, definir/ajustar a cor do próprio nível INFO para `<dim>`:
```python
logger.level("INFO", color="<dim>")
```
(isso mantém INFO funcionando, apenas apagado).

O `_FILE_FORMAT` (arquivo em disco) **não** deve ganhar cor — manter como está (loguru já remove tags de cor nos arquivos, mas não introduza tags novas no formato de arquivo).

### 3. Trocar os pontos de log para usar os níveis novos

- **Datasets**: em `binance/usdm_futures/orchestration/handlers/data.py`, a linha-resumo de datasets atualizados (`log.info(f"[{symbol}] Datasets atualizados: ...")`) deve passar a usar o nível `DATASET`:
  ```python
  log.log("DATASET", f"[{symbol}] Datasets atualizados: ...")
  ```
- **Abertura de posição**: no handler de execução que loga a abertura de posição (procurar por mensagens como "Abrindo posição" / "Posição aberta" em `binance/usdm_futures/orchestration/handlers/`), trocar `log.info(...)` por `log.log("POS_OPEN", ...)`.
- **Fechamento de posição**: no handler que loga o encerramento (procurar "Posição encerrada" / fechamento em `binance/usdm_futures/orchestration/handlers/`), trocar para `log.log("POS_CLOSE", ...)`.

Todos os demais `logger.info`/`log.info` do sistema permanecem como INFO (ficarão apagados via `<dim>`, que é o desejado para rotina).

## Restrições

- Não alterar `triple_ema.py`.
- Não mexer em ERROR/WARNING.
- Não colorir o formato de arquivo (`_FILE_FORMAT`).
- Não criar parâmetros de config novos.
- Não alterar o conteúdo/texto das mensagens — só o nível/cor.

## Validação

1. Logs de rotina aparecem em cinza apagado.
2. A linha "Datasets atualizados: ..." aparece em ciano suave.
3. Abertura de posição em verde forte; fechamento em magenta forte.
4. ERROR/WARNING inalterados.
5. Os arquivos de log em disco continuam sem códigos de cor e com o formato atual.
