"""Custom exception hierarchy for the Gold Trading Bot.

Using specific exceptions instead of broad 'except Exception'
makes debugging much easier and prevents hiding real problems.
"""

from enum import Enum


class ErrorCategory(Enum):
    """Classify errors for consistent recovery behavior.

    TEMPORARY: Retry on next tick (network blip, rate limit, timeout)
    PERMANENT: Fail and log — needs human intervention (bad config, auth)
    UNKNOWN:   Activate kill switch as fail-safe
    """
    TEMPORARY = "temporary"
    PERMANENT = "permanent"
    UNKNOWN = "unknown"


def classify_error(exc: Exception) -> ErrorCategory:
    """Classify an exception into a recovery category."""
    import asyncio

    if isinstance(exc, (
        BrokerConnectionError, ConnectionError, TimeoutError, OSError,
        asyncio.TimeoutError,
        ConfirmationTimeoutError, ConfirmationRejectedError,
    )):
        return ErrorCategory.TEMPORARY
    # RateLimitError lives in broker_client — check by class name to avoid circular import
    if type(exc).__name__ == "RateLimitError":
        return ErrorCategory.TEMPORARY
    if isinstance(exc, (ConfigurationError, BrokerAuthError, ModelNotLoadedError)):
        return ErrorCategory.PERMANENT
    if isinstance(exc, GoldBotError):
        return ErrorCategory.TEMPORARY  # Most trading errors are retryable
    return ErrorCategory.UNKNOWN


class GoldBotError(Exception):
    """Base exception for all trading bot errors."""


# -- Data errors --------------------------------------------------------------

class DataError(GoldBotError):
    """Market data fetch or processing error."""


class InsufficientDataError(DataError):
    """Not enough candle data to calculate indicators."""


# -- AI / Prediction errors ---------------------------------------------------

class PredictionError(GoldBotError):
    """ML model prediction error."""


class ModelNotLoadedError(PredictionError):
    """ML models are not loaded or not trained yet."""


# -- Order / Execution errors -------------------------------------------------

class OrderExecutionError(GoldBotError):
    """Order submission or confirmation error."""


class DuplicateOrderError(OrderExecutionError):
    """Attempted to open a duplicate order in the same direction."""


# -- Risk errors --------------------------------------------------------------

class RiskRejectedError(GoldBotError):
    """Trade was rejected by risk management checks."""


class KillSwitchActiveError(RiskRejectedError):
    """Kill switch is active, all trading stopped."""


# -- Configuration errors -----------------------------------------------------

class ConfigurationError(GoldBotError):
    """Invalid configuration or missing required settings."""


# -- Broker errors ------------------------------------------------------------

class BrokerError(GoldBotError):
    """Error communicating with Capital.com broker API."""


class BrokerAuthError(BrokerError):
    """Authentication with broker failed."""


class BrokerConnectionError(BrokerError):
    """Cannot connect to broker API."""


# -- Confirmation errors (semi-auto mode) -------------------------------------

class ConfirmationTimeoutError(GoldBotError):
    """WhatsApp confirmation timed out."""


class ConfirmationRejectedError(GoldBotError):
    """User rejected the signal via WhatsApp."""
