"""Application configuration -- loads from .env file via pydantic-settings.

Usage:
    from config.settings import get_settings
    cfg = get_settings()
    print(cfg.capital_email_masked)
"""

import os
from datetime import time
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dataclasses import dataclass as stdlib_dataclass

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


def _resolve_env_file() -> str:
    """Locate the .env file outside OneDrive-synced storage.

    Resolution order: $GOLD_ENV_PATH, ~/secrets/ai-trading-gold/.env, ./.env.
    """
    override = os.environ.get("GOLD_ENV_PATH")
    if override and Path(override).exists():
        return override
    external = Path.home() / "secrets" / "ai-trading-gold" / ".env"
    if external.exists():
        return str(external)
    return ".env"


_ENV_FILE_PATH = _resolve_env_file()


@stdlib_dataclass
class InstrumentConfig:
    """Instrument-specific parameters for XAUUSD."""
    symbol: str = "GOLD"
    pip_size: float = 0.01
    lot_unit: str = "oz"
    margin_factor: float = 0.05
    default_slippage: float = 0.30
    spread_threshold: float = 0.50


class Settings(BaseSettings):
    """All settings loaded from environment variables / .env file."""

    # -- Broker (Capital.com) -------------------------------------------------
    capital_email: str = ""
    capital_password: str = ""
    capital_api_key: str = ""
    capital_demo: bool = True

    # -- Database (PostgreSQL) ------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "gold_trader"
    postgres_user: str = "trader"
    postgres_password: str = Field(
        default="",
        description="PostgreSQL password. MUST be set in .env",
    )

    # -- Trading --------------------------------------------------------------
    trading_mode: Literal["auto", "semi_auto"] = "auto"
    trading_interval_seconds: int = 60
    position_check_seconds: int = 30
    timeframes: list[str] = ["5m", "15m", "1h"]
    min_confidence: float = 0.55
    min_trade_score: int = 60
    confirmation_timeout_seconds: int = 120

    # -- Risk -----------------------------------------------------------------
    max_risk_per_trade_pct: float = 2.0
    max_daily_loss_pct: float = 5.0
    max_weekly_loss_pct: float = 10.0
    max_open_positions: int = 1
    max_trades_per_day: int = 80
    kill_switch_drawdown_pct: float = 20.0
    max_consecutive_losses: int = 5
    cooldown_minutes: int = 30
    max_spread_pips: float = 3.0
    trading_start_hour: int = 8
    trading_start_minute: int = 0
    trading_end_hour: int = 22
    trading_end_minute: int = 0

    # -- Advanced Risk / Position Sizing (Phase 9) ----------------------------
    kelly_mode: str = "half"               # "full", "half", "quarter"
    atr_baseline: float = 3.0             # Normal XAUUSD ATR-14 on 5min candles
    max_portfolio_heat_pct: float = 5.0   # RISK-03: max total open risk %
    equity_curve_ema_period: int = 20     # RISK-05: lookback for equity EMA
    equity_curve_filter_enabled: bool = True  # RISK-05: enable/disable equity curve filter
    monte_carlo_paths: int = 1000         # RISK-04: number of MC simulation paths

    # -- Notifications (Twilio WhatsApp) --------------------------------------
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_from_number: str = ""
    twilio_to_number: str = ""
    notifications_enabled: bool = True

    # -- API ------------------------------------------------------------------
    api_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # -- Instrument -----------------------------------------------------------
    instrument: InstrumentConfig = Field(default_factory=InstrumentConfig, exclude=True)

    # -- Data Retention -------------------------------------------------------
    candle_retention_days: int = 180

    # -- Logging --------------------------------------------------------------
    log_level: str = "INFO"

    # -- MiroFish Swarm Intelligence (Phase 6) --------------------------------
    mirofish_enabled: bool = False           # Opt-in; False = graceful fallback (D-16)
    mirofish_url: str = "http://localhost:5001"
    mirofish_cache_ttl_seconds: int = 360    # 6 minutes -- cached result validity (D-11)
    mirofish_poll_interval_seconds: int = 300  # 5 minutes -- background sim frequency (D-10)
    mirofish_max_sims_per_day: int = 48      # MIRO-06: max daily simulations
    mirofish_token_budget_per_day: int = 200_000  # MIRO-06: ~$0.04/day at gpt-4o-mini rates
    mirofish_simulation_timeout_seconds: float = 180.0  # 3 min max per simulation
    mirofish_max_rounds: int = 15            # OASIS simulation rounds cap

    # -- Economic Calendar (Phase 8) -------------------------------------------
    calendar_enabled: bool = True
    calendar_fetch_interval_minutes: int = 360  # Refresh every 6 hours
    calendar_block_minutes_before: int = 30     # Block trades N min before high-impact
    calendar_cooldown_minutes_after: int = 15   # Wait N min after high-impact
    calendar_force_close_on_extreme: bool = True  # Close positions on extreme events (NFP, FOMC, CPI)

    # -- News Sentiment Analysis (Phase 11) -----------------------------------
    sentiment_enabled: bool = False           # Opt-in; False = graceful fallback
    sentiment_model: Literal["vader", "finbert"] = "vader"  # NLP model selection
    sentiment_poll_interval_seconds: int = 300  # 5 minutes (SENT-01)
    sentiment_retention_days: int = 30        # Keep 30 days of headlines
    sentiment_min_keywords: int = 1           # Min gold keywords to accept article
    sentiment_seed_update_hours: int = 1      # MiroFish seed refresh cadence
    sentiment_finbert_cache_path: str = ""    # TRANSFORMERS_CACHE override (Windows-safe)
    sentiment_halflife_minutes: int = 30      # EWM decay halflife
    sentiment_source_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "kitco": 1.0,
            "investing": 0.9,
            "marketwatch": 0.8,
            "goldbroker": 0.7,
        }
    )

    # -- Inter-Market Correlations (Phase 12) ---------------------------------
    correlation_enabled: bool = False           # Opt-in; False = graceful fallback (snapshot=None)
    correlation_cache_ttl_seconds: int = 3600    # 1h TTL (RESEARCH Pitfall 3: yfinance rate limits)
    correlation_lookback_days: int = 200          # Need >=120 for corr_*_120 (RESEARCH Pitfall 2)

    # -- Exit AI Specialist (Phase 14) ----------------------------------------
    exit_ai_enabled: bool = False               # Opt-in for AI-driven trade management
    exit_ai_saved_models_dir: str = "ai_engine/saved_models"

    # -- Order Flow / Orderbuch Analysis (Phase 13) ---------------------------
    orderflow_enabled: bool = False              # Opt-in; False = graceful OHLCV-only fallback
    orderflow_quote_enrichment_enabled: bool = False  # Optional Capital.com L1 quote quantities
    orderflow_profile_window: int = 200          # Candles for rolling POC/VAH/VAL profile
    orderflow_profile_bins: int = 40             # Price bins used by volume-profile approximation
    orderflow_liquidity_window: int = 20         # Lookback for liquidity-zone distances
    orderflow_absorption_window: int = 20        # Lookback for absorption and volume z-scores

    # -------------------------------------------------------------------------
    # Computed properties
    # -------------------------------------------------------------------------

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def trading_start(self) -> time:
        return time(self.trading_start_hour, self.trading_start_minute)

    @property
    def trading_end(self) -> time:
        return time(self.trading_end_hour, self.trading_end_minute)

    # -------------------------------------------------------------------------
    # Validation
    # -------------------------------------------------------------------------

    @field_validator("capital_api_key", "capital_password")
    @classmethod
    def validate_broker_secret(cls, v: str, info) -> str:
        # Allow empty during test/import; reject explicit blank-or-whitespace
        # only when an env value was actively provided. Pydantic passes through
        # the raw env string, so we treat whitespace-only as invalid.
        if v is None:
            raise ValueError(f"{info.field_name} must not be None")
        if isinstance(v, str) and v != "" and v.strip() == "":
            raise ValueError(
                f"{info.field_name} must not be empty/whitespace-only"
            )
        return v

    @field_validator("api_port", "postgres_port")
    @classmethod
    def validate_port_range(cls, v: int, info) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(
                f"{info.field_name} must be in range 1-65535 (current: {v})"
            )
        return v

    @field_validator("max_risk_per_trade_pct")
    @classmethod
    def validate_risk(cls, v: float) -> float:
        if v <= 0 or v > 10:
            raise ValueError("max_risk_per_trade_pct must be between 0 and 10")
        return v

    @field_validator("trading_interval_seconds")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v < 10:
            raise ValueError(
                "trading_interval_seconds must be >= 10 (current: %d)" % v
            )
        return v

    @field_validator("sentiment_poll_interval_seconds")
    @classmethod
    def validate_sentiment_interval(cls, v: int) -> int:
        if v < 60:
            raise ValueError(
                "sentiment_poll_interval_seconds must be >= 60"
            )
        return v

    @field_validator("trading_start_hour", "trading_end_hour")
    @classmethod
    def validate_hours(cls, v: int) -> int:
        if not (0 <= v <= 23):
            raise ValueError(
                "Trading hour must be between 0 and 23 (current: %d)" % v
            )
        return v

    def validate_required(self) -> list[str]:
        """Return list of missing/invalid fields. Empty = OK."""
        import os

        errors: list[str] = []

        # Broker credentials (always required for trading)
        if not self.capital_email:
            errors.append("CAPITAL_EMAIL is required")
        if not self.capital_password:
            errors.append("CAPITAL_PASSWORD is required")
        if not self.capital_api_key:
            errors.append("CAPITAL_API_KEY is required")

        # Database: PostgreSQL password only required if no SQLite fallback
        sqlite_fallback = os.getenv("SQLITE_FALLBACK", "false").lower() in (
            "1", "true", "yes",
        )
        has_database_url = bool(os.getenv("DATABASE_URL", ""))
        if not self.postgres_password and not sqlite_fallback and not has_database_url:
            errors.append(
                "POSTGRES_PASSWORD is required. "
                "Or set SQLITE_FALLBACK=true for local operation."
            )

        # Semi-auto mode requires Twilio
        if self.trading_mode == "semi_auto" and self.notifications_enabled:
            if not self.twilio_account_sid or not self.twilio_auth_token:
                errors.append(
                    "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN are required "
                    "in semi_auto mode"
                )

        # Cross-field validation warnings (non-fatal)
        warnings: list[str] = []
        if self.trading_interval_seconds < 10:
            warnings.append(
                f"TRADING_INTERVAL={self.trading_interval_seconds}s is very low "
                "(recommended: >= 10s)"
            )
        if self.max_trades_per_day > 20:
            warnings.append(
                f"MAX_TRADES_PER_DAY={self.max_trades_per_day} is unusually high "
                "(recommended: <= 20)"
            )
        if self.min_confidence < 0.5:
            warnings.append(
                f"MIN_CONFIDENCE={self.min_confidence} is below 0.5 (coin-flip level)"
            )

        if warnings:
            import logging
            logger = logging.getLogger(__name__)
            for w in warnings:
                logger.warning("Config warning: %s", w)

        return errors

    # Sensitive fields that must never appear in logs
    _SENSITIVE_FIELDS = frozenset({
        "capital_password", "capital_api_key", "postgres_password",
        "twilio_auth_token", "twilio_account_sid",
    })

    def __repr__(self) -> str:
        """Mask sensitive fields in repr output."""
        fields = []
        for name in self.model_fields:
            val = getattr(self, name, "")
            if name in self._SENSITIVE_FIELDS and val:
                fields.append(f"{name}='***'")
            else:
                fields.append(f"{name}={val!r}")
        return f"Settings({', '.join(fields)})"

    @property
    def postgres_url_safe(self) -> str:
        """DB URL with password masked -- safe for logging."""
        if self.postgres_password:
            return self.postgres_url.replace(self.postgres_password, "***")
        return self.postgres_url

    @property
    def capital_email_masked(self) -> str:
        """Broker email with local part masked -- safe for logs/docstrings."""
        if not self.capital_email or "@" not in self.capital_email:
            return "***"
        local, _, domain = self.capital_email.partition("@")
        if len(local) <= 2:
            return f"***@{domain}"
        return f"{local[0]}***{local[-1]}@{domain}"

    model_config = {
        "env_file": _ENV_FILE_PATH,
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return singleton Settings instance."""
    return Settings()
