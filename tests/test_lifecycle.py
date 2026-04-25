"""Startup and shutdown lifecycle tests.

Verifies health check failures, graceful shutdown behavior,
and timeout handling during system lifecycle.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from market_data.broker_client import BrokerError


# ---------------------------------------------------------------------------
# Health Check Tests
# ---------------------------------------------------------------------------


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_fails_on_db_error(self):
        """Database initialization fails → startup aborted."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
        )

        with patch("trading.lifecycle.init_db", AsyncMock(side_effect=Exception("DB connection refused"))):
            from main import TradingSystem
            system = TradingSystem(settings)

            with pytest.raises(RuntimeError, match="health check failed"):
                await system._health_check()

    @pytest.mark.asyncio
    async def test_health_check_fails_on_broker_auth_error(self):
        """Broker authentication fails → startup aborted."""
        from config.settings import Settings

        settings = Settings(
            capital_email="bad@test.com",
            capital_password="wrong",
            capital_api_key="invalid",
        )

        with patch("trading.lifecycle.init_db", AsyncMock()):
            from main import TradingSystem
            system = TradingSystem(settings)
            system.broker.authenticate = AsyncMock(
                side_effect=BrokerError("Auth failed: 401")
            )

            with pytest.raises(RuntimeError, match="health check failed"):
                await system._health_check()

    @pytest.mark.asyncio
    async def test_health_check_warns_on_missing_models(self):
        """No AI models → warning (not failure)."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
        )

        with patch("trading.lifecycle.init_db", AsyncMock()), \
             patch("os.path.isdir", return_value=False):
            from main import TradingSystem
            system = TradingSystem(settings)
            system.broker.authenticate = AsyncMock()

            # Should not raise — AI models are optional
            await system._health_check()

    @pytest.mark.asyncio
    async def test_health_check_passes_all(self):
        """All components healthy → no exception."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
            notifications_enabled=False,
        )

        with patch("trading.lifecycle.init_db", AsyncMock()), \
             patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["xgboost_gold.pkl"]):
            from main import TradingSystem
            system = TradingSystem(settings)
            system.broker.authenticate = AsyncMock()

            await system._health_check()  # Should not raise


# ---------------------------------------------------------------------------
# Graceful Shutdown Tests
# ---------------------------------------------------------------------------


class TestGracefulShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_sets_running_false(self):
        """Shutdown stops the trading loop."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
        )

        from main import TradingSystem
        system = TradingSystem(settings)
        system._running = True

        # Mock broker and DB
        system.broker.close = AsyncMock()
        system.orders = MagicMock()
        system.orders.get_open_count.return_value = 0

        with patch("trading.lifecycle.close_db", AsyncMock()):
            await system.stop()

        assert not system._running

    @pytest.mark.asyncio
    async def test_shutdown_with_open_positions_reconciles(self):
        """Shutdown with open positions → reconciliation attempted."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
        )

        from main import TradingSystem
        system = TradingSystem(settings)
        system._running = True

        system.broker.close = AsyncMock()
        system.orders = MagicMock()
        system.orders.get_open_count.return_value = 2
        system.orders.position_monitor = MagicMock()
        system.orders.position_monitor.sync_with_broker = AsyncMock(
            return_value={"synced": ["D1", "D2"], "orphaned": []}
        )

        with patch("trading.lifecycle.close_db", AsyncMock()):
            await system.stop()

        system.orders.position_monitor.sync_with_broker.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_reconciliation_timeout(self):
        """Reconciliation takes too long → timeout handled gracefully."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
        )

        from main import TradingSystem
        system = TradingSystem(settings)
        system._running = True

        system.broker.close = AsyncMock()
        system.orders = MagicMock()
        system.orders.get_open_count.return_value = 1

        async def slow_sync():
            await asyncio.sleep(100)  # Way too slow
            return {"synced": [], "orphaned": []}

        system.orders.position_monitor = MagicMock()
        system.orders.position_monitor.sync_with_broker = AsyncMock(
            side_effect=slow_sync
        )

        with patch("trading.lifecycle.close_db", AsyncMock()):
            # Should not hang — timeout kicks in
            await asyncio.wait_for(system.stop(), timeout=20)

        assert not system._running

    @pytest.mark.asyncio
    async def test_shutdown_kill_switch_closes_all(self):
        """Kill switch active at shutdown → close all positions."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
        )

        from main import TradingSystem
        system = TradingSystem(settings)
        system._running = True

        system.risk.force_kill_switch("test shutdown")
        system.broker.close = AsyncMock()
        system.orders = MagicMock()
        system.orders.close_all = AsyncMock(return_value=2)
        system.orders.get_open_count.return_value = 0
        system.notifications = MagicMock()
        system.notifications.notify_kill_switch = MagicMock()

        with patch("trading.lifecycle.close_db", AsyncMock()):
            await system.stop()

        system.orders.close_all.assert_called_once()


# ---------------------------------------------------------------------------
# Configuration Validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_missing_broker_credentials(self):
        """Missing broker credentials → validation error."""
        from config.settings import Settings
        import os

        # Override env to ensure empty credentials
        with patch.dict(os.environ, {
            "CAPITAL_EMAIL": "",
            "CAPITAL_PASSWORD": "",
            "CAPITAL_API_KEY": "",
            "SQLITE_FALLBACK": "true",
        }, clear=False):
            settings = Settings(
                capital_email="",
                capital_password="",
                capital_api_key="",
                _env_file=None,
            )
            errors = settings.validate_required()
            assert len(errors) > 0
            assert any("CAPITAL_EMAIL" in e for e in errors)

    def test_valid_config_no_errors(self):
        """All required fields set → no errors."""
        from config.settings import Settings
        import os

        with patch.dict(os.environ, {"SQLITE_FALLBACK": "true"}):
            settings = Settings(
                capital_email="test@test.com",
                capital_password="pass",
                capital_api_key="key123",
            )
            errors = settings.validate_required()
            assert len(errors) == 0

    def test_semi_auto_requires_twilio(self):
        """Semi-auto mode without Twilio → error."""
        from config.settings import Settings

        settings = Settings(
            capital_email="test@test.com",
            capital_password="pass",
            capital_api_key="key123",
            trading_mode="semi_auto",
            notifications_enabled=True,
            twilio_account_sid="",
            twilio_auth_token="",
        )
        errors = settings.validate_required()
        assert any("TWILIO" in e for e in errors)
