"""Service layer for control app API workflows."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, desc
from sqlalchemy.orm import Session

from backend.app.config import load_settings
from backend.app.database import get_session
from backend.app.guards import GuardViolation, validate_command_guard
from backend.app.models import ActionLog, AppSettings, ErrorLog
from integration.goldbot_adapter import GoldBotAdapter
from shared.contracts import (
    ActionLogEntry,
    BotMetricsResponse,
    BotStatusResponse,
    CommandRequest,
    CommandResponse,
    ErrorLogEntry,
    SettingsResponse,
    SettingsUpdateRequest,
    TradeChartPoint,
)


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def parse_db_datetime(value: str | datetime | None) -> datetime | None:
    """Parse SQLite datetime values into aware UTC datetime objects."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class ControlService:
    """Coordinates API calls, validation, integration adapter and storage."""

    def __init__(self, adapter: GoldBotAdapter) -> None:
        self._adapter = adapter
        self._settings = load_settings()

    def _ensure_settings(self, session: Session) -> AppSettings:
        row = session.get(AppSettings, 1)
        if row is None:
            row = AppSettings(id=1, polling_interval_seconds=3, confirmations_enabled=True)
            session.add(row)
            session.commit()
            session.refresh(row)
        return row

    def _purge_old_logs(self, session: Session) -> None:
        cutoff = utc_now() - timedelta(days=self._settings.retention_days)
        session.execute(delete(ActionLog).where(ActionLog.executed_at < cutoff))
        session.execute(delete(ErrorLog).where(ErrorLog.created_at < cutoff))
        session.commit()

    def _log_error(self, session: Session, error_code: str, message: str, details: str) -> None:
        session.add(
            ErrorLog(
                source="backend",
                error_code=error_code,
                message=message,
                details=details,
                created_at=utc_now(),
            )
        )
        session.commit()

    def get_status(self) -> BotStatusResponse:
        payload = self._adapter.get_status()
        return BotStatusResponse(**payload)

    def get_metrics(self) -> BotMetricsResponse:
        payload = self._adapter.get_metrics()
        return BotMetricsResponse(**payload)

    def submit_command(self, command: CommandRequest) -> CommandResponse:
        with get_session() as session:
            app_settings = self._ensure_settings(session)
            self._purge_old_logs(session)

            try:
                validate_command_guard(command, app_settings.confirmations_enabled)
                message = self._adapter.execute_command(command.command_type, command.target, command.params)
                executed_at = utc_now()
                action = ActionLog(
                    command_id=command.command_id,
                    command_type=command.command_type.value,
                    target=command.target,
                    params_json=json.dumps(command.params, ensure_ascii=True),
                    status="success",
                    message=message,
                    requested_by=command.requested_by,
                    requested_at=command.requested_at,
                    executed_at=executed_at,
                )
                session.add(action)
                session.commit()
                return CommandResponse(
                    accepted=True,
                    command_id=command.command_id,
                    command_type=command.command_type,
                    status="success",
                    message=message,
                    executed_at=executed_at,
                )
            except GuardViolation as exc:
                executed_at = utc_now()
                session.add(
                    ActionLog(
                        command_id=command.command_id,
                        command_type=command.command_type.value,
                        target=command.target,
                        params_json=json.dumps(command.params, ensure_ascii=True),
                        status="blocked",
                        message=str(exc),
                        requested_by=command.requested_by,
                        requested_at=command.requested_at,
                        executed_at=executed_at,
                    )
                )
                session.commit()
                self._log_error(session, "GUARD_BLOCKED", str(exc), details=command.model_dump_json())
                raise
            except Exception as exc:
                executed_at = utc_now()
                session.add(
                    ActionLog(
                        command_id=command.command_id,
                        command_type=command.command_type.value,
                        target=command.target,
                        params_json=json.dumps(command.params, ensure_ascii=True),
                        status="failed",
                        message=str(exc),
                        requested_by=command.requested_by,
                        requested_at=command.requested_at,
                        executed_at=executed_at,
                    )
                )
                session.commit()
                self._log_error(
                    session,
                    "COMMAND_FAILED",
                    "Command execution failed.",
                    details=str(exc),
                )
                raise

    def list_actions(self, limit: int = 100) -> list[ActionLogEntry]:
        with get_session() as session:
            self._purge_old_logs(session)
            rows = (
                session.query(ActionLog)
                .order_by(desc(ActionLog.executed_at))
                .limit(limit)
                .all()
            )
            return [
                ActionLogEntry(
                    id=row.id,
                    command_id=row.command_id,
                    command_type=row.command_type,
                    target=row.target,
                    params=json.loads(row.params_json or "{}"),
                    status=row.status,
                    message=row.message,
                    requested_by=row.requested_by,
                    requested_at=row.requested_at,
                    executed_at=row.executed_at,
                )
                for row in rows
            ]

    def list_errors(self, limit: int = 100) -> list[ErrorLogEntry]:
        with get_session() as session:
            self._purge_old_logs(session)
            rows = (
                session.query(ErrorLog)
                .order_by(desc(ErrorLog.created_at))
                .limit(limit)
                .all()
            )
            return [
                ErrorLogEntry(
                    id=row.id,
                    source=row.source,
                    error_code=row.error_code,
                    message=row.message,
                    details=row.details,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def get_settings(self) -> SettingsResponse:
        with get_session() as session:
            row = self._ensure_settings(session)
            return SettingsResponse(
                polling_interval_seconds=row.polling_interval_seconds,
                confirmations_enabled=row.confirmations_enabled,
                updated_at=row.updated_at,
            )

    def update_settings(self, update: SettingsUpdateRequest) -> SettingsResponse:
        with get_session() as session:
            row = self._ensure_settings(session)
            if update.polling_interval_seconds is not None:
                row.polling_interval_seconds = update.polling_interval_seconds
            if update.confirmations_enabled is not None:
                row.confirmations_enabled = update.confirmations_enabled
            row.updated_at = utc_now()
            session.add(row)
            session.commit()
            session.refresh(row)
            return SettingsResponse(
                polling_interval_seconds=row.polling_interval_seconds,
                confirmations_enabled=row.confirmations_enabled,
                updated_at=row.updated_at,
            )

    def get_trade_chart_points(self, days: int = 14, limit: int = 400) -> list[TradeChartPoint]:
        """Read trade entry/SL/TP data from the main gold_bot database."""
        source_db = self._settings.source_db_path
        if not source_db.exists():
            return []

        cutoff = utc_now() - timedelta(days=max(1, days))
        query = """
            SELECT
                id,
                deal_id,
                opened_at,
                closed_at,
                direction,
                status,
                entry_price,
                stop_loss,
                take_profit,
                exit_price,
                lot_size,
                net_pnl
            FROM trades
            WHERE opened_at IS NOT NULL
            ORDER BY opened_at DESC
            LIMIT ?
        """

        points: list[TradeChartPoint] = []
        with sqlite3.connect(str(source_db)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, (max(1, limit),)).fetchall()

        for row in reversed(rows):
            opened_at = parse_db_datetime(row["opened_at"])
            if opened_at is None or opened_at < cutoff:
                continue

            points.append(
                TradeChartPoint(
                    id=int(row["id"]),
                    deal_id=row["deal_id"],
                    opened_at=opened_at,
                    closed_at=parse_db_datetime(row["closed_at"]),
                    direction=str(row["direction"] or "UNKNOWN"),
                    status=str(row["status"] or "UNKNOWN"),
                    entry_price=float(row["entry_price"]),
                    stop_loss=float(row["stop_loss"]) if row["stop_loss"] is not None else None,
                    take_profit=float(row["take_profit"]) if row["take_profit"] is not None else None,
                    exit_price=float(row["exit_price"]) if row["exit_price"] is not None else None,
                    lot_size=float(row["lot_size"]) if row["lot_size"] is not None else None,
                    net_pnl=float(row["net_pnl"]) if row["net_pnl"] is not None else None,
                )
            )
        return points


def build_control_service() -> ControlService:
    """Factory for control service instance."""
    return ControlService(adapter=GoldBotAdapter())
