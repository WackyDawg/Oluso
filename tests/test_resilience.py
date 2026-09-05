from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aegistwin.api import create_app
from aegistwin.schemas import (
    AccountCreate,
    BehaviorEventIn,
    Channel,
    EventType,
    OutageHeartbeatRequest,
    OutageSimulationRequest,
    ReconciliationRequest,
    ResilienceMode,
)
from aegistwin.service import AtoService, ConflictError


def payment(account: str, event_id: str, at: datetime, recipient: str = "known-merchant") -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account,
        occurred_at=at,
        event_type=EventType.TRANSFER,
        channel=Channel.USSD,
        amount=2_000,
        available_balance_before=20_000,
        recipient_id=recipient,
        sim_id="known-sim",
        interaction_ms=14_000,
        menu_depth=5,
        navigation_signature="ussd_1_2_1",
    )


def signed_heartbeat(
    service: AtoService,
    *,
    nonce: str,
    core: bool = True,
    external: bool = True,
) -> OutageHeartbeatRequest:
    request = OutageHeartbeatRequest(
        source_id="trusted-bank-health",
        observed_at=datetime.now(UTC),
        nonce=nonce,
        core_banking_available=core,
        telco_gateway_available=external,
        consortium_available=external,
        recipient_graph_available=external,
        model_runtime_available=external,
        signature="0" * 64,
    )
    return request.model_copy(update={"signature": service.sign_resilience_heartbeat(request)})


def test_signed_heartbeat_replay_protection_and_capsule(test_settings) -> None:
    service = AtoService(test_settings)
    unsigned = signed_heartbeat(service, nonce="heartbeat-invalid-001", external=False)
    invalid = unsigned.model_copy(update={"signature": "f" * 64})
    with pytest.raises(ConflictError, match="signature"):
        service.resilience_heartbeat(invalid)

    heartbeat = signed_heartbeat(service, nonce="heartbeat-valid-001", external=False)
    state = service.resilience_heartbeat(heartbeat)
    assert state["context"]["mode"] == "degraded"
    assert state["context"]["capsule_valid"] is True
    with pytest.raises(ConflictError, match="nonce"):
        service.resilience_heartbeat(heartbeat)


def test_degraded_mode_lowers_confidence_freezes_learning_and_uses_safety_envelope(
    test_settings,
) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="degraded", display_name="Degraded"))
    now = datetime.now(UTC)
    service.score_event(payment("degraded", "known_history", now - timedelta(days=2)))
    service.resilience_heartbeat(
        signed_heartbeat(service, nonce="heartbeat-degraded-002", external=False)
    )

    decision = service.score_event(
        payment("degraded", "degraded_new_recipient", now, recipient="new-recipient")
    )
    assert decision.resilience.mode == ResilienceMode.DEGRADED
    assert decision.resilience.confidence_multiplier <= 0.72
    assert decision.resilience.safety_envelope_applied is True
    assert decision.policy.requires_trusted_confirmation is True
    assert decision.learning["trust_state"] == "excluded"
    assert "model_runtime" in decision.resilience.unavailable_sources


def test_isolated_payment_is_pending_journalled_and_reconciled_exactly_once(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="isolated", display_name="Isolated"))
    now = datetime.now(UTC)
    service.score_event(payment("isolated", "isolated_history", now - timedelta(days=3)))
    service.simulate_resilience_mode(OutageSimulationRequest(mode=ResilienceMode.ISOLATED))

    decision = service.score_event(
        payment("isolated", "isolated_payment", now, recipient="new-offline-recipient")
    )
    assert decision.resilience.mode == ResilienceMode.ISOLATED
    assert decision.resilience.offline_reference.startswith("OFF-")
    assert decision.policy.action.value in {
        "reversible_settlement_delay",
        "reversible_hold_and_review",
    }
    assert "no money has been moved" in decision.customer_explanation.lower()
    assert service.database.verify_offline_journal("default")["valid"] is True
    assert service.resilience_status()["pending_journal_events"] == 1

    restored = service.simulate_resilience_mode(
        OutageSimulationRequest(mode=ResilienceMode.ONLINE)
    )
    assert restored["context"]["mode"] == "reconciling"
    reconciliation = service.reconcile_outage(ReconciliationRequest(batch_size=10))
    assert reconciliation["status"] == "completed"
    assert reconciliation["processed"] == 1
    assert reconciliation["duplicate_actions"] == 0
    assert reconciliation["final_mode"] == "online"
    repeated = service.reconcile_outage(ReconciliationRequest(batch_size=10))
    assert repeated["status"] == "already_reconciled"
    assert repeated["duplicate_actions"] == 0


def test_offline_journal_detects_payload_tampering(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="tamper", display_name="Tamper"))
    service.simulate_resilience_mode(OutageSimulationRequest(mode=ResilienceMode.ISOLATED))
    service.score_event(payment("tamper", "tamper_event", datetime.now(UTC)))
    assert service.database.verify_offline_journal("default")["valid"] is True
    with service.database.connect() as connection:
        connection.execute(
            "UPDATE offline_journal SET payload_json=? WHERE event_id=?",
            ('{"altered":true}', "tamper_event"),
        )
    verification = service.database.verify_offline_journal("default")
    assert verification["valid"] is False
    assert verification["first_invalid_journal_id"]


def test_resilience_api_is_role_separated(test_settings) -> None:
    client = TestClient(create_app(test_settings))
    integration = {"X-API-Key": test_settings.api_key}
    auditor = {"X-API-Key": test_settings.auditor_api_key}
    admin = {"X-API-Key": test_settings.admin_api_key}
    assert client.post(
        "/v1/resilience/simulate", headers=integration, json={"mode": "isolated"}
    ).status_code == 403
    changed = client.post(
        "/v1/resilience/simulate", headers=admin, json={"mode": "isolated"}
    )
    assert changed.status_code == 200
    assert changed.json()["context"]["mode"] == "isolated"
    status = client.get("/v1/resilience/status", headers=integration)
    assert status.status_code == 200
    assert status.json()["mode"] == "isolated"
    assert client.get("/v1/resilience/journal/verify", headers=integration).status_code == 403
    assert client.get("/v1/resilience/journal/verify", headers=auditor).status_code == 200


def test_recovery_storm_controller_is_bounded_and_risk_prioritised(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="storm", display_name="Storm"))
    now = datetime.now(UTC)
    service.simulate_resilience_mode(OutageSimulationRequest(mode=ResilienceMode.ISOLATED))
    service.score_event(payment("storm", "storm_low", now, recipient="known"))
    high = payment("storm", "storm_high", now + timedelta(seconds=1), recipient="new-high").model_copy(
        update={"amount": 18_000, "available_balance_before": 20_000, "sim_id": "new-sim"}
    )
    service.score_event(high)
    service.simulate_resilience_mode(OutageSimulationRequest(mode=ResilienceMode.ONLINE))

    first = service.reconcile_outage(ReconciliationRequest(batch_size=1))
    assert first["status"] == "partial"
    assert first["processed"] == 1
    assert first["remaining"] == 1
    assert first["score_changes"][0]["event_id"] == "storm_high"
    assert first["priority_order"] == "risk_descending_then_original_sequence"
    assert first["circuit_breaker_open"] is False
    second = service.reconcile_outage(ReconciliationRequest(batch_size=10))
    assert second["status"] == "completed"
    assert second["remaining"] == 0
