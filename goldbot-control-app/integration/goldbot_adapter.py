"""Adapter between control app and the existing gold_bot domain."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared.contracts import BotState, CommandType


def utc_now() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class BotRuntimeState:
    """In-memory runtime state; replace internals with real domain wiring."""

    started_at: datetime = field(default_factory=utc_now)
    state: BotState = BotState.STOPPED
    active_strategy: str = "xau-usd-intraday-v1"
    open_positions: int = 0
    risk_state: str = "normal"
    last_error: str | None = None
    orders_today: int = 0
    successful_commands_24h: int = 0
    failed_commands_24h: int = 0


class GoldBotAdapter:
    """Thin adapter API consumed by the backend service layer."""

    def __init__(self) -> None:
        self._state = BotRuntimeState()

    def get_status(self) -> dict:
        """Fetch current status from bot runtime."""
        return {
            "state": self._state.state,
            "uptime_sec": int((utc_now() - self._state.started_at).total_seconds()),
            "last_heartbeat": utc_now(),
            "active_strategy": self._state.active_strategy,
            "open_positions": self._state.open_positions,
            "risk_state": self._state.risk_state,
            "last_error": self._state.last_error,
        }

    def get_metrics(self) -> dict:
        """Fetch dashboard metrics."""
        return {
            "orders_today": self._state.orders_today,
            "successful_commands_24h": self._state.successful_commands_24h,
            "failed_commands_24h": self._state.failed_commands_24h,
            "api_latency_ms": 18.4,
            "db_latency_ms": 4.9,
        }

    def execute_command(self, command_type: CommandType, target: str | None, params: dict) -> str:
        """Execute a supported command against the runtime.

        This default implementation keeps the system safe and local-only.
        Swap internals with real trading system calls when ready.
        """
        del target, params
        if command_type == CommandType.START_BOT:
            self._state.state = BotState.RUNNING
            self._state.risk_state = "normal"
            self._state.successful_commands_24h += 1
            return "Bot gestartet."

        if command_type == CommandType.STOP_BOT:
            self._state.state = BotState.STOPPED
            self._state.successful_commands_24h += 1
            return "Bot gestoppt."

        if command_type == CommandType.PAUSE_TRADING:
            self._state.state = BotState.PAUSED
            self._state.successful_commands_24h += 1
            return "Trading pausiert."

        if command_type == CommandType.RESUME_TRADING:
            self._state.state = BotState.RUNNING
            self._state.risk_state = "normal"
            self._state.successful_commands_24h += 1
            return "Trading fortgesetzt."

        if command_type == CommandType.RELOAD_CONFIG:
            self._state.successful_commands_24h += 1
            return "Konfiguration neu geladen."

        if command_type == CommandType.EMERGENCY_STOP:
            self._state.state = BotState.STOPPED
            self._state.risk_state = "emergency_stop"
            self._state.successful_commands_24h += 1
            return "Not-Aus ausgeführt."

        self._state.failed_commands_24h += 1
        self._state.last_error = f"Unknown command: {command_type}"
        raise ValueError(f"Unsupported command type: {command_type}")

    def get_ai_decision(self) -> dict:
        """Return current AI decision-stack snapshot.

        Real AI wiring (xgb+lgbm ensemble + exit-AI + risk gates) should
        replace this stub. The shape is the production contract used by the
        Mission-Control UI; values here are deterministic-but-time-varying
        so the UI animates believably during demo and dev.
        """
        now = utc_now()
        t = time.time() % 600.0

        # Smooth oscillating confidence values (0.55 .. 0.92).
        core_conf = 0.55 + 0.18 * (math.sin(t / 17.0) * 0.5 + 0.5)
        spec_conf = 0.50 + 0.22 * (math.sin(t / 23.0 + 1.2) * 0.5 + 0.5)
        exit_conf = 0.60 + 0.20 * (math.sin(t / 13.0 + 2.1) * 0.5 + 0.5)

        action = "BUY" if math.sin(t / 31.0) >= 0 else "SELL"
        if self._state.state in (BotState.STOPPED, BotState.PAUSED):
            action = "HOLD"

        agree = spec_conf >= 0.62
        if action == "HOLD":
            exit_signal = "HOLD"
        elif exit_conf > 0.8:
            exit_signal = "TIGHTEN"
        else:
            exit_signal = "HOLD"

        risk_state = (self._state.risk_state or "normal").lower()
        if risk_state in ("emergency_stop", "hot"):
            risk_decision = "BLOCK"
            heat = "HIGH"
        elif core_conf > 0.85 or spec_conf > 0.85:
            risk_decision = "ALLOW"
            heat = "MEDIUM"
        else:
            risk_decision = "ALLOW"
            heat = "LOW"

        if action == "HOLD":
            final = "HOLD"
        elif risk_decision == "BLOCK":
            final = "REJECT"
        elif agree and core_conf > 0.7:
            final = "ENTER"
        else:
            final = "WAIT_FOR_EXECUTION_WINDOW"

        regime_idx = int((t / 60.0)) % 4
        regime = ["BREAKOUT", "TREND", "RANGE", "TREND"][regime_idx]

        ai_mode = "PAUSED" if self._state.state == BotState.PAUSED else "LIVE_SHADOW"

        return {
            "core": {"action": action, "confidence": round(core_conf, 3)},
            "specialist": {"agree": agree, "confidence": round(spec_conf, 3)},
            "exit": {"signal": exit_signal, "confidence": round(exit_conf, 3)},
            "risk": {"decision": risk_decision, "heat": heat},
            "final_action": final,
            "regime": regime,
            "ai_mode": ai_mode,
            "timestamp": now,
        }
