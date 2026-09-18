from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from oluso.api import create_app


def test_api_auth_and_scoring(test_settings) -> None:
    client = TestClient(create_app(test_settings))
    assert client.get("/health").status_code == 200
    assert client.get("/v1/metrics").status_code == 401
    headers = {"X-API-Key": test_settings.api_key}

    account = client.post(
        "/v1/accounts",
        headers=headers,
        json={"account_id": "api_account", "display_name": "API Account"},
    )
    assert account.status_code == 201

    event = client.post(
        "/v1/events/score",
        headers=headers,
        json={
            "event_id": "api_event_001",
            "account_id": "api_account",
            "occurred_at": datetime.now(UTC).isoformat(),
            "event_type": "purchase",
            "channel": "app",
            "amount": 1000,
            "recipient_id": "merchant_one",
            "device_id": "device_one",
            "sim_id": "sim_one",
        },
    )
    assert event.status_code == 201
    payload = event.json()
    assert payload["account_id"] == "api_account"
    assert "feature_snapshot" in payload
    assert payload["customer_explanation"].endswith(".")
    assert payload["evidence"]["mode"] == "core_banking_fallback"
    assert "audit_hash" in payload

    audit = client.get(
        "/v1/audit/verify", headers={"X-API-Key": test_settings.auditor_api_key}
    )
    assert audit.status_code == 200
    assert audit.json()["valid"] is True
