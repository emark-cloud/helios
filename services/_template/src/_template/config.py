"""Shared base settings. Each service subclasses with its own SERVICE_PREFIX."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """Common settings every Helios service needs.

    Subclass this in each service and add service-specific fields. The
    `model_config["env_prefix"]` should be set per-subclass so env vars
    don't collide between services.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Networking ───────────────────────────────────────────
    http_host: str = Field(default="0.0.0.0", description="HTTP bind host")
    http_port: int = Field(default=8000, description="HTTP bind port")

    # ── Storage ──────────────────────────────────────────────
    database_url: str = Field(
        default="postgres://helios:helios@localhost:5432/helios",
        validation_alias="DATABASE_URL",
    )

    # ── Chains ───────────────────────────────────────────────
    kite_rpc_url: str = Field(default="", validation_alias="KITE_RPC_URL")
    kite_chain_id: int = Field(default=2368, validation_alias="KITE_CHAIN_ID")

    # ── Indexer ──────────────────────────────────────────────
    goldsky_endpoint: str = Field(default="", validation_alias="GOLDSKY_ENDPOINT")

    # ── Modes ────────────────────────────────────────────────
    scenario_mode: bool = Field(default=False, validation_alias="SCENARIO_MODE")
    scenario_file: str = Field(
        default="scenarios/phase1-drawdown.json",
        validation_alias="SCENARIO_FILE",
    )

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")

    # ── CORS ─────────────────────────────────────────────────
    # Comma-separated list of allowed origins. In `development` we accept
    # the local frontend by default; production deploys must set this to
    # the public frontend host(s). `"*"` is rejected by FastAPI when paired
    # with `allow_credentials=True`, so the list must be explicit.
    cors_allowed_origins: str = Field(
        default="http://localhost:3000",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]
