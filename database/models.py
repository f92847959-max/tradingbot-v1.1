"""SQLAlchemy ORM models for all database tables."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    JSON,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# Use JSONB on PostgreSQL and plain JSON on SQLite/other engines.
JSON_COMPAT = JSON().with_variant(JSONB, "postgresql")


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    open: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    volume: Mapped[float | None] = mapped_column(Numeric(15, 2))
    spread: Mapped[float | None] = mapped_column(Numeric(6, 2))

    __table_args__ = (
        Index("uq_candles_tf_ts", "timestamp", "timeframe", unique=True),
        Index("idx_candles_tf_ts", "timeframe", timestamp.desc()),
    )


# ---------------------------------------------------------------------------
# AI Signals
# ---------------------------------------------------------------------------

class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    action: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY, SELL, HOLD
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    trade_score: Mapped[int | None] = mapped_column(Integer)
    entry_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(10, 2))
    take_profit: Mapped[float | None] = mapped_column(Numeric(10, 2))
    model_votes: Mapped[dict | None] = mapped_column(JSON_COMPAT)
    reasoning: Mapped[dict | None] = mapped_column(JSON_COMPAT)
    top_features: Mapped[dict | None] = mapped_column(JSON_COMPAT)
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    timeframe: Mapped[str | None] = mapped_column(String(10))

    __table_args__ = (
        Index("idx_signals_executed_ts", "was_executed", "timestamp"),
    )


class GovernanceDecision(Base):
    __tablename__ = "governance_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    preliminary_action: Mapped[str] = mapped_column(String(4), nullable=False)
    final_action: Mapped[str] = mapped_column(String(4), nullable=False)
    gate_decision: Mapped[str] = mapped_column(String(10), nullable=False)
    regime: Mapped[str | None] = mapped_column(String(20))
    confidence_before: Mapped[float | None] = mapped_column(Numeric(6, 4))
    final_confidence: Mapped[float | None] = mapped_column(Numeric(6, 4))
    conflict_ratio: Mapped[float | None] = mapped_column(Numeric(6, 4))
    global_score: Mapped[float | None] = mapped_column(Numeric(6, 4))
    gate_reasons: Mapped[list | None] = mapped_column(JSON_COMPAT)
    threshold_source: Mapped[str | None] = mapped_column(String(80))
    threshold_confidence: Mapped[float | None] = mapped_column(Numeric(6, 4))
    threshold_margin: Mapped[float | None] = mapped_column(Numeric(6, 4))
    artifact_version: Mapped[str | None] = mapped_column(String(120))
    was_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    evaluation_summary: Mapped[dict | None] = mapped_column(JSON_COMPAT)

    __table_args__ = (
        Index("idx_governance_decisions_ts", timestamp.desc()),
        Index("idx_governance_decisions_gate_ts", "gate_decision", "timestamp"),
    )


class ModelMetadata(Base):
    __tablename__ = "model_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    trained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accuracy: Mapped[float | None] = mapped_column(Numeric(5, 4))
    f1_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    feature_count: Mapped[int | None] = mapped_column(Integer)
    sample_count: Mapped[int | None] = mapped_column(Integer)
    file_path: Mapped[str | None] = mapped_column(Text)
    config: Mapped[dict | None] = mapped_column(JSON_COMPAT)


# ---------------------------------------------------------------------------
# Trades & Orders
# ---------------------------------------------------------------------------

class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    deal_id: Mapped[str | None] = mapped_column(Text, unique=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    direction: Mapped[str] = mapped_column(String(4), nullable=False)  # BUY, SELL
    entry_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    exit_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    stop_loss: Mapped[float | None] = mapped_column(Numeric(10, 2))
    take_profit: Mapped[float | None] = mapped_column(Numeric(10, 2))
    lot_size: Mapped[float] = mapped_column(Numeric(8, 4), nullable=False)
    spread_at_entry: Mapped[float | None] = mapped_column(Numeric(6, 2))
    slippage: Mapped[float | None] = mapped_column(Numeric(6, 2))
    pnl_pips: Mapped[float | None] = mapped_column(Numeric(8, 2))
    pnl_euros: Mapped[float | None] = mapped_column(Numeric(12, 2))
    fees: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    net_pnl: Mapped[float | None] = mapped_column(Numeric(12, 2))
    close_reason: Mapped[str | None] = mapped_column(String(20))
    trade_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    ai_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    trade_score: Mapped[int | None] = mapped_column(Integer)
    timeframe: Mapped[str | None] = mapped_column(String(10))
    session: Mapped[str | None] = mapped_column(String(20))
    reasoning: Mapped[dict | None] = mapped_column(JSON_COMPAT)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="OPEN")

    __table_args__ = (
        Index("idx_trades_status", "status"),
        Index("idx_trades_closed_at", "closed_at"),
        Index("idx_trades_opened_at", opened_at.desc()),
    )


class OrderLog(Base):
    __tablename__ = "order_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    action: Mapped[str] = mapped_column(String(15), nullable=False)
    deal_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON_COMPAT)


# ---------------------------------------------------------------------------
# Risk Management
# ---------------------------------------------------------------------------

class RiskEvent(Base):
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON_COMPAT)


class DailyRiskState(Base):
    __tablename__ = "daily_risk_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    equity_start: Mapped[float | None] = mapped_column(Numeric(12, 2))
    equity_peak: Mapped[float | None] = mapped_column(Numeric(12, 2))
    max_drawdown_pct: Mapped[float | None] = mapped_column(Numeric(6, 4))
    daily_pnl: Mapped[float | None] = mapped_column(Numeric(12, 2))
    consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    kill_switch_activated: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("idx_daily_risk_state_date", "date"),
    )


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class DailyStats(Base):
    __tablename__ = "daily_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    equity_start: Mapped[float | None] = mapped_column(Numeric(12, 2))
    equity_end: Mapped[float | None] = mapped_column(Numeric(12, 2))
    trades_total: Mapped[int] = mapped_column(Integer, default=0)
    trades_won: Mapped[int] = mapped_column(Integer, default=0)
    trades_lost: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float | None] = mapped_column(Numeric(5, 4))
    gross_profit: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    gross_loss: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    net_pnl: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    profit_factor: Mapped[float | None] = mapped_column(Numeric(8, 4))
    max_drawdown: Mapped[float | None] = mapped_column(Numeric(6, 4))
    max_consecutive_losses: Mapped[int] = mapped_column(Integer, default=0)
    avg_trade_duration_seconds: Mapped[int | None] = mapped_column(Integer)
    total_spread_cost: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    total_slippage: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    __table_args__ = (
        Index("idx_daily_stats_date", "date"),
    )


class EquityCurve(Base):
    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    trade_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("trades.id", ondelete="CASCADE")
    )


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    message_preview: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # SENT, FAILED, QUEUED
    error_message: Mapped[str | None] = mapped_column(Text)


# ---------------------------------------------------------------------------
# Semi-Auto Confirmations
# ---------------------------------------------------------------------------

class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    signal_data: Mapped[dict] = mapped_column(JSON_COMPAT, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING, APPROVED, REJECTED, EXPIRED
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)


# ---------------------------------------------------------------------------
# Economic Calendar
# ---------------------------------------------------------------------------

class EconomicEventRecord(Base):
    __tablename__ = "economic_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    country: Mapped[str] = mapped_column(String(10), nullable=False)
    impact: Mapped[str] = mapped_column(String(10), nullable=False)  # low/medium/high
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast: Mapped[str | None] = mapped_column(String(50))
    previous: Mapped[str | None] = mapped_column(String(50))
    actual: Mapped[str | None] = mapped_column(String(50))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("idx_econ_events_time", "event_time"),
        Index("uq_econ_events", "title", "event_time", unique=True),
    )


# ---------------------------------------------------------------------------
# News Sentiment (Phase 11)
# ---------------------------------------------------------------------------

class NewsSentiment(Base):
    __tablename__ = "news_sentiment"

    id: Mapped[int] = mapped_column(primary_key=True)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    entry_id: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    source_weight: Mapped[float] = mapped_column(Numeric(4, 3), default=1.0, nullable=False)
    keywords_matched: Mapped[list | None] = mapped_column(JSON_COMPAT)
    model_used: Mapped[str] = mapped_column(String(20), default="vader", nullable=False)

    __table_args__ = (
        Index("idx_news_sentiment_published", "published_at"),
        Index("idx_news_sentiment_source", "source"),
        Index("uq_news_sentiment_entry_id", "entry_id", unique=True),
    )
