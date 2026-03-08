"""Shared constants for the Gold Intraday Trading System."""

import enum


class TradeDirection(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSING = "CLOSING"
    CLOSED = "CLOSED"
    CLOSE_FAILED = "CLOSE_FAILED"
    ORPHANED = "ORPHANED"


class SignalAction(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

# ---------------------------------------------------------------------------
# Gold / Capital.com
# ---------------------------------------------------------------------------

GOLD_EPIC = "GOLD"          # Capital.com Epic for XAU/USD
PIP_SIZE = 0.01             # 1 pip = $0.01 for Gold CFD
CONTRACT_SIZE = 1.0         # 1 lot = 1 Troy Ounce (Capital.com CFD)
GOLD_SYMBOL = "XAU/USD"

# ---------------------------------------------------------------------------
# Timeframes
# ---------------------------------------------------------------------------

TIMEFRAMES = ["5m", "15m", "1h"]
DEFAULT_TIMEFRAME = "5m"
SIGNAL_TIMEFRAME = "5m"
CONFIRMATION_TIMEFRAME = "15m"
TREND_TIMEFRAME = "1h"

# Candle counts used for indicators
MIN_CANDLES_FOR_INDICATORS = 50
DEFAULT_CANDLE_COUNT = 200

# ---------------------------------------------------------------------------
# Trading Sessions (UTC hours/minutes — canonical source of truth)
# ---------------------------------------------------------------------------

LONDON_OPEN_HOUR = 7
LONDON_OPEN_MINUTE = 0
LONDON_CLOSE_HOUR = 16
LONDON_CLOSE_MINUTE = 30

NY_OPEN_HOUR = 13
NY_OPEN_MINUTE = 0
NY_CLOSE_HOUR = 22
NY_CLOSE_MINUTE = 0

OVERLAP_START_HOUR = 13
OVERLAP_START_MINUTE = 0
OVERLAP_END_HOUR = 16
OVERLAP_END_MINUTE = 30

ASIA_OPEN_HOUR = 23
ASIA_OPEN_MINUTE = 0
ASIA_CLOSE_HOUR = 7
ASIA_CLOSE_MINUTE = 0

# String representations for display
LONDON_OPEN_UTC = "07:00"
LONDON_CLOSE_UTC = "16:30"
NY_OPEN_UTC = "13:00"
NY_CLOSE_UTC = "22:00"
OVERLAP_START_UTC = "13:00"
OVERLAP_END_UTC = "16:30"

SESSION_NAMES = ["London", "NewYork", "Overlap", "Off"]

# ---------------------------------------------------------------------------
# Risk Defaults
# ---------------------------------------------------------------------------

MAX_SPREAD_PIPS = 3.0
DEFAULT_RISK_PCT = 2.0
DEFAULT_MAX_DAILY_LOSS_PCT = 5.0
DEFAULT_MAX_WEEKLY_LOSS_PCT = 10.0
DEFAULT_KILL_SWITCH_DRAWDOWN_PCT = 20.0
DEFAULT_MAX_OPEN_POSITIONS = 3
DEFAULT_MAX_TRADES_PER_DAY = 80
DEFAULT_MAX_CONSECUTIVE_LOSSES = 5
DEFAULT_COOLDOWN_MINUTES = 30

# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

MIN_TRADE_SCORE = 60
MIN_AI_CONFIDENCE = 0.70
SL_ATR_MULTIPLIER = 1.5
TP_ATR_MULTIPLIER = 2.0
MIN_RR_RATIO = 1.5

# Regime Detection Defaults
ADX_TREND_THRESHOLD = 25.0
ADX_RANGE_THRESHOLD = 20.0
ATR_VOLATILE_RATIO = 1.5
REGIME_LOOKBACK_PERIODS = 20
REGIME_MIN_CONFIRM_CANDLES = 3

# ---------------------------------------------------------------------------
# Semi-Auto Mode
# ---------------------------------------------------------------------------

DEFAULT_CONFIRMATION_TIMEOUT_SECONDS = 120
CONFIRMATION_APPROVE_KEYWORDS = {"YES", "Y", "JA", "J", "1"}
CONFIRMATION_REJECT_KEYWORDS = {"NO", "N", "NEIN", "0"}
