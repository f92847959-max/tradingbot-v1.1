from datetime import datetime, timezone

AUTH_HEADERS = {"X-Control-Token": "test-token"}


def test_health_endpoint(client) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "goldbot-control-backend"


def test_private_route_requires_token(client) -> None:
    response = client.get("/api/v1/settings")
    assert response.status_code == 401


def test_block_critical_command_without_confirm(client) -> None:
    payload = {
        "command_id": "cmd-critical-1",
        "command_type": "STOP_BOT",
        "target": "trading-engine",
        "params": {},
        "requested_by": "tester",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/v1/bot/commands", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 400
    assert "confirm_token='CONFIRM'" in response.json()["detail"]


def test_accept_non_critical_command_and_log_action(client) -> None:
    payload = {
        "command_id": "cmd-ok-1",
        "command_type": "PAUSE_TRADING",
        "target": "trading-engine",
        "params": {"reason": "manual check"},
        "requested_by": "tester",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    response = client.post("/api/v1/bot/commands", json=payload, headers=AUTH_HEADERS)
    assert response.status_code == 200
    assert response.json()["accepted"] is True

    actions = client.get("/api/v1/logs/actions", headers=AUTH_HEADERS)
    assert actions.status_code == 200
    items = actions.json()
    assert len(items) >= 1
    assert any(item["command_id"] == "cmd-ok-1" for item in items)


def test_settings_roundtrip(client) -> None:
    current = client.get("/api/v1/settings", headers=AUTH_HEADERS)
    assert current.status_code == 200
    assert current.json()["polling_interval_seconds"] == 3

    update = client.put(
        "/api/v1/settings",
        json={"polling_interval_seconds": 5, "confirmations_enabled": True},
        headers=AUTH_HEADERS,
    )
    assert update.status_code == 200
    payload = update.json()
    assert payload["polling_interval_seconds"] == 5
    assert payload["confirmations_enabled"] is True


def test_trade_chart_points(client) -> None:
    response = client.get("/api/v1/trades/chart?days=30&limit=20", headers=AUTH_HEADERS)
    assert response.status_code == 200
    points = response.json()
    assert len(points) >= 1
    first = points[0]
    assert first["deal_id"] == "D-TEST-1"
    assert first["entry_price"] == 2050.5
    assert first["stop_loss"] == 2046.0
    assert first["take_profit"] == 2058.5
