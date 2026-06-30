# USDM Futures Bot

Robô trader assíncrono e multipar para futuros perpétuos USDT (USDM) na Binance.

Projeto em **reconstrução incremental**: cada etapa é validada manualmente em
notebooks antes de avançar para a próxima. A lógica de negócio vive sempre nos
módulos Python sob `usdm_futures/`; os notebooks servem apenas para validação.

## Estrutura (em construção)

Por enquanto existe apenas o esqueleto do pacote `usdm_futures/`. As demais
camadas (configuração, infraestrutura, domínio, serviços, máquina de estados e
aplicação) serão adicionadas etapa por etapa.

## Ambiente

Requer Python 3.13+. As dependências são adicionadas conforme cada etapa as exige.