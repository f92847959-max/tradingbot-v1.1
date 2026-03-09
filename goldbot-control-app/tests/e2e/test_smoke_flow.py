from datetime import datetime, timezone

AUTH_HEADERS = {"X-Control-Token": "test-token"}


def test_smoke_status_command_logs_flow(client) -> None:
    status_before = client.get("/api/v1/bot/status", headers=AUTH_HEADERS)
    assert status_before.status_code == 200
    assert status_before.json()["state"] in {"RUNNING", "STOPPED", "PAUSED", "DEGRADED"}

    command_payload = {
        "command_id": "cmd-smoke-1",
        "command_type": "START_BOT",
        "target": "trading-engine",
        "params": {"source": "smoke-test"},
        "requested_by": "smoke",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }
    command = client.post("/api/v1/bot/commands", json=command_payload, headers=AUTH_HEADERS)
    assert command.status_code == 200
    assert command.json()["status"] == "success"

    status_after = client.get("/api/v1/bot/status", headers=AUTH_HEADERS)
    assert status_after.status_code == 200
    assert status_after.json()["state"] == "RUNNING"

    actions = client.get("/api/v1/logs/actions?limit=10", headers=AUTH_HEADERS)
    assert actions.status_code == 200
    assert any(item["command_id"] == "cmd-smoke-1" for item in actions.json())
