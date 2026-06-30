"""Ponto de entrada assíncrono: descobre TOMLs de pares e inicia execução multipar."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

from ..config.schedule import load_system_settings
from ..config.secrets import Secrets
from ..logging.logger import setup_logging
from .bootstrap import build_symbol_runner

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SYSTEM_TOML = _PROJECT_ROOT / "binance" / "system_toml" / "system_settings.toml"
_PAIRS_DIR = _PROJECT_ROOT / "binance" / "symbol_toml"
_LOG_DIR = _PROJECT_ROOT / "logs"


async def main() -> None:
    # 1. Carrega configurações do sistema
    try:
        sys_settings = load_system_settings(str(_SYSTEM_TOML))
    except Exception as exc:
        logger.critical(f"Falha ao carregar configurações do sistema: {exc}")
        sys.exit(1)

    # 2. Carrega credenciais
    try:
        secrets = Secrets()
    except Exception as exc:
        logger.critical(f"Falha ao carregar credenciais: {exc}")
        sys.exit(1)

    # 3. Configura logging
    setup_logging(sys_settings.logging, _LOG_DIR)
    logger.info("Bot USDM Futures iniciado.")

    # 4. Descobre TOMLs de pares
    if not _PAIRS_DIR.exists():
        logger.critical(f"Diretório de pares não encontrado: {_PAIRS_DIR}")
        sys.exit(1)

    toml_paths = sorted(_PAIRS_DIR.glob("*.toml"))
    if not toml_paths:
        logger.critical(f"Nenhum arquivo .toml encontrado em: {_PAIRS_DIR}")
        sys.exit(1)

    logger.info(f"{len(toml_paths)} arquivo(s) de par encontrado(s).")

    # 5. Inicializa runners (sequencial para conexões independentes por par)
    pairs: list[tuple] = []
    for toml_path in toml_paths:
        try:
            runner, client = await build_symbol_runner(
                str(toml_path), sys_settings, secrets
            )
            pairs.append((runner, client))
            logger.info(f"Par '{toml_path.name}' inicializado.")
        except Exception as exc:
            logger.error(f"Falha ao inicializar '{toml_path.name}': {exc}. Par ignorado.")

    if not pairs:
        logger.critical("Nenhum par inicializado com sucesso. Encerrando.")
        sys.exit(1)

    logger.info(f"{len(pairs)} par(es) ativo(s). Iniciando execução concorrente...")

    # 6. Executa todos os pares concorrentemente
    tasks: list[asyncio.Task] = [
        asyncio.create_task(runner.run(), name=getattr(runner, "_symbol", f"par-{i}"))
        for i, (runner, _) in enumerate(pairs)
    ]

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for task, result in zip(tasks, results):
            if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                logger.error(f"Par '{task.get_name()}' encerrou com erro: {result}")
    except asyncio.CancelledError:
        logger.info("Encerramento solicitado. Aguardando tarefas...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        logger.info("Fechando conexões com a exchange...")
        for _, client in pairs:
            try:
                await client.close()
            except Exception as exc:
                logger.warning(f"Erro ao fechar conexão: {exc}")
        logger.info("Bot encerrado.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
