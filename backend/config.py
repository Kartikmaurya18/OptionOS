from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars (see .env.example)."""

    delta_rest_url: str = "https://api.india.delta.exchange"
    delta_ws_url: str = "wss://socket.india.delta.exchange"

    # One DeltaOptionsStreamer shard runs per asset here, each with its own
    # OptionStore + SymbolResolver, all publishing onto the same Redis
    # channel with an `asset` tag -- see websocket/manager.py for the
    # per-client subscription filtering that uses that tag.
    assets: list[str] = ["BTC", "ETH"]
    underlying: str = "BTC"  # default asset a freshly connected client is subscribed to

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    ws_reconnect_min_delay: float = 1.0
    ws_reconnect_max_delay: float = 30.0
    ws_ping_interval: float = 25.0

    # Redis is the fan-out seam between the Market Data Service (publisher)
    # and any number of WebSocket Gateway instances (subscribers) -- see
    # services/message_bus.py.
    redis_url: str = "redis://localhost:6379/0"
    redis_channel: str = "ticks"

    model_config = SettingsConfigDict(env_prefix="STRADDLE_", env_file=".env")


settings = Settings()


def spot_index_symbol(asset: str) -> str:
    """Delta's convention for an asset's perpetual/index symbol, used to
    source its live spot price -- e.g. 'BTC' -> 'BTCUSD'."""
    return f"{asset}USD"
