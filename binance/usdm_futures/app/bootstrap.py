"""Composition root: monta as dependências concretas e retorna um SymbolRunner pronto."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..config.schedule import SystemSettings
from ..config.secrets import Secrets
from ..config.strategy_config import load_strategy_settings
from ..config.symbol_config import AssetSettings, DataConfig, load_asset_settings
from ..domain.state_machine.transitions import RunContext
from ..execution.order_executor import OrderExecutor
from ..execution.order_utils import OrderUtils
from ..execution.position_tracker import PositionTracker
from ..execution.protection_orders import ProtectionOrders
from ..infrastructure.exchange_client import ExchangeClient
from ..logging.logger import get_pair_logger
from ..market_data.memory_repository import MemoryRepository
from ..market_data.source import OHLCVSource
from ..market_data.transform import OHLCVTransform
from ..orchestration.symbol_runner import SymbolRunner
from ..shared.market_hours import MarketHoursChecker
from ..strategy import NullStrategy, TripleEmaStrategy


# Papel → nome do campo em DataConfig. "signal" é sempre preenchido; os
# demais são opcionais e só geram source/repo quando presentes no TOML.
_ROLE_TIMEFRAME_FIELDS: dict[str, str] = {
    "signal": "signal_timeframe",
    "trend": "trend_timeframe",
    "aux_1": "aux_timeframe_1",
    "aux_2": "aux_timeframe_2",
}


def _resolve_candle_limit(data: DataConfig, timeframe_ms: int) -> int:
    """Converte config de dados em quantidade de candles para o carregamento inicial."""
    if data.candle_limit is not None:
        return data.candle_limit
    if data.since is None:
        raise ValueError(
            "'since' precisa ser informado quando candle_limit não está definido"
        )
    since_dt = datetime.strptime(data.since, "%d/%m/%Y").replace(tzinfo=timezone.utc)
    since_ms = int(since_dt.timestamp() * 1000)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return max(1, (now_ms - since_ms) // timeframe_ms)


async def build_symbol_runner(
    toml_path: str,
    sys_settings: SystemSettings,
    secrets: Secrets,
) -> tuple[SymbolRunner, ExchangeClient]:
    """Carrega configuração do par, conecta à exchange e monta todas as dependências.

    Retorna (runner, client) — o cliente deve ser fechado pelo chamador no shutdown.
    Levanta exceção se o TOML for inválido ou a conexão falhar.
    """
    asset = load_asset_settings(toml_path)
    log = get_pair_logger(asset.symbol)

    # Config da estratégia: mora em binance/strategy_toml/<strategy>.toml
    # (pasta irmã de symbol_toml/). O nome do arquivo casa com asset.strategy.
    strategy_path = (
        Path(toml_path).parent.parent / "strategy_toml" / f"{asset.strategy}.toml"
    )
    strategy_settings = load_strategy_settings(str(strategy_path))

    # Seleciona credenciais conforme o modo sandbox do par
    if asset.sandbox:
        api_key = secrets.binance_test_api_key
        api_secret = secrets.binance_test_api_secret
    else:
        api_key = secrets.binance_prod_api_key
        api_secret = secrets.binance_prod_api_secret

    client = ExchangeClient(
        exchange_name=AssetSettings.exchange,
        api_key=api_key,
        api_secret=api_secret,
        market_type=AssetSettings.market_type,
        sandbox=asset.sandbox,
        log=log,
    )
    exchange = await client.connect()

    # --- Camada de execução ---
    utils = OrderUtils(exchange=exchange, symbol=asset.symbol)
    exc_cfg = sys_settings.execution

    protection = ProtectionOrders(
        exchange=exchange,
        symbol=asset.symbol,
        utils=utils,
        percent_sl=asset.risk.stop_loss_percent,
        percent_tp=asset.risk.take_profit_percent,
        leverage=asset.risk.leverage,
        sl_confirm_attempts=exc_cfg.sl_confirm_attempts,
        sl_confirm_delay=exc_cfg.sl_confirm_delay_seconds,
        log=log,
    )

    tracker = PositionTracker(
        exchange=exchange,
        symbol=asset.symbol,
        utils=utils,
        protection_orders=protection,
        leverage=asset.risk.leverage,
        margin_usdt=asset.orders.margin_usdt,
        fetch_positions_timeout=exc_cfg.fetch_positions_timeout_seconds,
        normalize_max_attempts=exc_cfg.normalize_max_attempts,
        normalize_retry_delay=exc_cfg.normalize_retry_delay_seconds,
        log=log,
    )

    executor = OrderExecutor(
        exchange=exchange,
        symbol=asset.symbol,
        utils=utils,
        protection_orders=protection,
        margin_usdt=asset.orders.margin_usdt,
        leverage=asset.risk.leverage,
        order_type=asset.orders.order_type,
        chase_percent=asset.orders.chase_percent,
        offset_percent=asset.orders.offset_percent,
        fill_timeout=asset.orders.fill_timeout,
        max_retries=asset.orders.max_retries,
        fetch_positions_timeout=exc_cfg.fetch_positions_timeout_seconds,
        log=log,
    )

    # --- Camada de dados de mercado ---
    # Um par (source + repo) por timeframe preenchido no TOML (1 a 4:
    # signal obrigatório; trend/aux_1/aux_2 opcionais). candle_limit/since
    # são únicos e aplicados a todos os datasets.
    fetch_cfg = sys_settings.fetch
    repos: dict[str, MemoryRepository] = {}
    timeframes: dict[str, str] = {}
    for role, field_name in _ROLE_TIMEFRAME_FIELDS.items():
        timeframe = getattr(asset.data, field_name)
        if timeframe is None:
            continue
        timeframes[role] = timeframe

        source = OHLCVSource(
            exchange=exchange,
            symbol=asset.symbol,
            timeframe=timeframe,
            log=log,
        )
        candle_limit = _resolve_candle_limit(asset.data, source.timeframe_ms)
        repos[role] = MemoryRepository(
            source=source,
            transform=OHLCVTransform(),
            candle_limit=candle_limit,
            max_rows=fetch_cfg.max_rows,
            batch_limit=fetch_cfg.batch_limit,
            fetch_retry_attempts=fetch_cfg.fetch_retry_attempts,
            fetch_retry_delay=fetch_cfg.fetch_retry_delay,
            log=log,
        )

    # --- Contexto da FSM ---
    mon_cfg = sys_settings.monitoring
    ctx = RunContext(
        has_symbol=True,
        max_cleanup_retries=mon_cfg.cleanup_max_retries,
        max_error_retries=mon_cfg.error_max_retries,
        max_monitoring_failures=mon_cfg.max_monitoring_failures,
        monitoring_heartbeat_every=mon_cfg.monitoring_heartbeat_every,
    )

    # Seleciona a implementação da estratégia pelo nome declarado no par.
    if asset.strategy == "triple-ema":
        strategy = TripleEmaStrategy(strategy_settings, timeframes, log)
    else:
        strategy = NullStrategy()

    runner = SymbolRunner(
        symbol=asset.symbol,
        ctx=ctx,
        hours_checker=MarketHoursChecker(sys_settings),
        system_settings=sys_settings,
        toml_path=toml_path,
        exchange_client=client,
        position_tracker=tracker,
        order_executor=executor,
        repos=repos,
        timeframes=timeframes,
        strategy=strategy,
        log=log,
    )

    return runner, client
