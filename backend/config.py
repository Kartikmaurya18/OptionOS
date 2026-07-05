from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, overridable via env vars (see .env.example)."""

    delta_rest_url: str = "https://api.india.delta.exchange"
    delta_ws_url: str = "wss://socket.india.delta.exchange"
    underlying: str = "BTC"
    # Delta's perpetual/index symbol used to source the live BTC spot price.
    spot_index_symbol: str = "BTCUSD"

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    ws_reconnect_min_delay: float = 1.0
    ws_reconnect_max_delay: float = 30.0
    ws_ping_interval: float = 25.0

    model_config = SettingsConfigDict(env_prefix="STRADDLE_", env_file=".env")


settings = Settings()
