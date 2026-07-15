# Tarefa: `amount` vira margem em USDT e SL/TP passam a considerar ROI (alavancagem)

## Regra inviolável

**NÃO ALTERAR, NÃO ABRIR e NÃO MENCIONAR o arquivo `binance/usdm_futures/strategy/triple_ema.py`.** Ignore-o completamente.

## Contexto

O bot opera Binance USDM Futures. Hoje há dois problemas na definição de ordens e proteções:

1. **`amount`** (em `[orders]` do TOML do par) é hoje a **quantidade da moeda** (ex.: `0.01` SOL). Queremos que passe a ser a **margem em dólar** (USDT) — o valor que sai do bolso do usuário — e o bot calcula a quantidade da moeda a partir disso.

2. **`stop_loss_percent` / `take_profit_percent`** (em `[risk]`) são hoje aplicados como **percentual sobre o movimento do preço**. Queremos que passem a representar **percentual de ROI** (retorno sobre a margem), o que exige considerar a **alavancagem** no cálculo do preço de disparo.

## Mudança 1 — `amount` → `margin_usdt` (margem em dólar)

### Semântica nova
- `margin_usdt` = margem em USDT (o que sai do bolso do usuário). Ex.: `1.0` = $1 de margem.
- posição (nocional) = `margin_usdt * leverage`. Ex.: $1 × 5 = $5 de posição.
- quantidade da moeda a enviar na ordem = `(margin_usdt * leverage) / preço_atual`.

### Onde alterar
- **TOML do par** (`binance/symbol_toml/*.toml`, seção `[orders]`): renomear o campo `amount` para `margin_usdt`. Ajustar o valor de exemplo para uma margem em dólar coerente (ex.: `margin_usdt = 1.0`).
- **`binance/usdm_futures/config/symbol_config.py`**: em `OrderConfig` (linha ~58), renomear o campo `amount` para `margin_usdt` (mantendo `float`, `Field(gt=0)`).
- **`binance/usdm_futures/app/bootstrap.py`**: hoje passa `amount=asset.orders.amount` para o `PositionTracker`/`OrderExecutor` (linhas ~110 e ~122). Atualizar para o novo campo. Como agora é margem (não quantidade), a quantidade real da ordem passa a ser **calculada em runtime** (ver abaixo), então o que é passado ao executor deve ser a **margem** (`margin_usdt`) e a **alavancagem**, não uma quantidade fixa.
- **`binance/usdm_futures/execution/order_executor.py`**: hoje o executor recebe `amount` (quantidade fixa) no `__init__` (linha ~23/36) e usa `self._amount` ao enviar ordens. Alterar para:
  - receber `margin_usdt` e `leverage` (a alavancagem já existe no config `risk.leverage`);
  - no momento de abrir a ordem, **calcular a quantidade** a partir do preço atual: `quantidade = (margin_usdt * leverage) / preço_atual`. Obter o preço atual da forma já usada no projeto (ticker/último preço disponível no executor ou via exchange).
  - aplicar `format_amount` (precisão) sobre a quantidade calculada, como já é feito hoje.
  - validar contra o mínimo do par (nocional/quantidade mínima). Se a quantidade calculada ficar abaixo do mínimo permitido pela exchange, logar erro claro e não enviar ordem inválida.

### Observações
- A quantidade deixa de ser fixa: cada entrada calcula a quantidade com o preço do momento. Isso é o comportamento desejado.
- Não introduzir novos parâmetros além de `margin_usdt` (a `leverage` já existe em `[risk]`).

## Mudança 2 — SL/TP por ROI (considerando alavancagem)

### Semântica nova
- `stop_loss_percent` e `take_profit_percent` passam a representar **percentual de ROI** (sobre a margem), não movimento de preço.
- Relação: `movimento_do_preço = percentual_ROI / leverage`.
- Ex.: `take_profit_percent = 3.0`, `leverage = 5` → o preço precisa mover `3 / 5 = 0.6%` para atingir 3% de ROI.

### Onde alterar
- **`binance/usdm_futures/execution/order_utils.py`**, método `calculate_protection_price` (linha ~43): hoje calcula `pct = percent / 100` e aplica direto sobre o preço. Alterar para **dividir o percentual pela alavancagem** antes de aplicar ao preço:
  - `pct = (percent / 100) / leverage`
  - Isso exige que o método tenha acesso ao valor de `leverage`. Passar a alavancagem para o método (ou para a classe que o contém) da forma mais limpa possível — a `leverage` está em `RiskConfig` e já é conhecida no bootstrap/execução. Preferir passar `leverage` como parâmetro do método `calculate_protection_price`, ou injetá-la na classe `OrderUtils` na construção. Escolher a opção mais coerente com a arquitetura atual.
  - O restante da fórmula (subtrair para long-SL / short-TP, somar para os demais; precisão via `price_to_precision`) permanece igual.
- **Quem chama `calculate_protection_price`** (em `protection_orders.py`, linhas ~118 e ~122): ajustar as chamadas para fornecer a `leverage` conforme a assinatura nova.

### Observação
- O objetivo é que uma posição que atinge o `take_profit_percent` de ROI seja de fato encerrada. Hoje, por medir movimento de preço, o TP fica muito distante quando há alavancagem (ex.: posição com +6% de ROI não encerra com TP de 3% "de preço"). Após a mudança, o TP de 3% (ROI) dispara com apenas 0.6% de movimento de preço (leverage 5x).

## Restrições

- Não alterar `triple_ema.py`.
- Não introduzir parâmetros de config novos além do renomeado `margin_usdt`.
- Preservar `format_amount`/`price_to_precision` e o respeito à precisão e aos mínimos da exchange.
- Não alterar a lógica de sinal/estratégia — apenas dimensionamento da ordem e cálculo de SL/TP.
- Manter "um par por execução".

## Validação

1. Com `margin_usdt = 1.0` e `leverage = 5`, ao abrir posição o bot calcula quantidade = `(1 * 5) / preço_atual`, respeitando precisão e mínimo do par.
2. Se a quantidade calculada ficar abaixo do mínimo do par, o bot loga erro claro e não envia ordem inválida.
3. Com `take_profit_percent = 3.0` e `leverage = 5`, o preço de TP corresponde a **0.6%** de movimento a partir da entrada (3% de ROI); o SL segue a mesma regra proporcional.
4. Uma posição que atinge o ROI-alvo é efetivamente encerrada pelo TP.
5. Nenhuma referência remanescente ao antigo campo `amount` em `[orders]` (renomeado para `margin_usdt`).
