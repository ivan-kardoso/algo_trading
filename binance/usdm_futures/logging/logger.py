import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from ..config.schedule import LoggingConfig

if TYPE_CHECKING:
    from loguru import Logger

_log_dir: Path | None = None
_config: LoggingConfig | None = None
_registered_pairs: set[str] = set()

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>"
)
_FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{line} | {message}"
)


def setup_logging(config: LoggingConfig, log_dir: Path) -> None:
    global _log_dir, _config
    _log_dir = log_dir
    _config = config

    log_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()

    logger.level("INFO", color="<dim>")
    logger.level("DATASET", no=22, color="<dim><cyan>")
    logger.level("POS_OPEN", no=23, color="<green><bold>")
    logger.level("POS_CLOSE", no=24, color="<magenta><bold>")

    logger.add(
        sys.stderr,
        level="INFO",
        format=_CONSOLE_FORMAT,
        colorize=True,
    )


def get_pair_logger(symbol: str) -> Logger:
    if _log_dir is None or _config is None:
        raise RuntimeError("Chame setup_logging() antes de get_pair_logger().")

    clean = symbol.split(":")[0].replace("/", "").lower()

    if clean not in _registered_pairs:
        _registered_pairs.add(clean)
        logger.add(
            _log_dir / f"{clean}.log",
            level="INFO",
            format=_FILE_FORMAT,
            filter=lambda record, c=clean: record["extra"].get("pair") in (c, None),
            rotation=_config.log_max_bytes,
            retention=_config.log_backup_count,
            encoding="utf-8",
        )

    return logger.bind(pair=clean)
