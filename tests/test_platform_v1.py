from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aegistwin.api import create_app
from aegistwin.platform import campaign_is_eligible, campaign_score, psi
from aegistwin.schemas import (
    AccountCreate,
    AppealRequest,
    BehaviorEventIn,
    Channel,
    ConsortiumReportRequest,
    EventType,
    FeedbackLabel,
    FeedbackRequest,
    LifecycleState,
    LifecycleTransitionRequest,
    PolicySimulationRequest,
    PrivacyRequest,
    ProfileSuccessionRequest,
    TelcoAssurance,
)
from aegistwin.service import AtoService, ConflictError, NotFoundError


def event(account: str, event_id: str, at: datetime, *, recipient: str = "merchant") -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account,
        occurred_at=at,
        event_type=EventType.TRANSFER,
        channel=Channel.APP,
        amount=2_000,
        available_balance_before=20_000,
        recipient_id=recipient,
        device_id="known-device",
        sim_id="known-sim",
        interaction_ms=15_000,
        menu_depth=5,
    )


def test_safe_learning_quarantine_maturation_and_delearning(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="learn", display_name="Learning"))
    now = datetime.now(UTC)
    decision = service.score_event(event("learn", "learn_current", now))
    assert decision.learning["trust_state"] == "pending"
    assert service.get_profile("learn").transaction_events == 0

    matured = service.mature_learning(now + timedelta(hours=25))
    assert matured["matured_events"] == 1
    assert service.get_profile("learn").transaction_events == 1

    service.add_feedback(
        decision.decision_id,
        FeedbackRequest(label=FeedbackLabel.ACCOUNT_TAKEOVER, analyst_id="analyst-a"),
    )
    assert service.database.get_event_trust("learn_current")["trust_state"] == "revoked"
    assert service.get_profile("learn").transaction_events == 0


def test_exact_replay_and_idempotent_transaction_lifecycle(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="replay", display_name="Replay"))
    decision = service.score_event(event("replay", "replay_event", datetime.now(UTC)))
    replay = service.replay_decision(decision.decision_id)
    assert replay["exact_match"] is True
    assert len(replay["replay_digest"]) == 64
    transition = LifecycleTransitionRequest(
        target_state=LifecycleState.SETTLED,
        actor_id="settlement-worker",
        reason="bank settlement confirmed",
        idempotency_key="settle-replay-event-001",
    )
    first = service.transition_lifecycle("replay_event", transition)
    second = service.transition_lifecycle("replay_event", transition)
    assert first["state"] == "settled"
    assert second["idempotent_replay"] is True


def test_campaign_guard_and_cross_account_propagation(test_settings) -> None:
    assert campaign_is_eligible(["ordinary"]) is False
    assert campaign_score(100, ["ordinary"]) == 0.0
    assert campaign_is_eligible(["new_channel", "recipient_change", "cashout"]) is True

    service = AtoService(test_settings)
    now = datetime.now(UTC)
    decisions = []
    for index in range(4):
        account = f"campaign_{index}"
        service.create_account(AccountCreate(account_id=account, display_name=account))
        service.score_event(event(
            account, f"campaign_baseline_{index}", now - timedelta(days=3), recipient="known-shop"
        ))
        attack = event(account, f"campaign_event_{index}", now + timedelta(seconds=index), recipient="mule-x").model_copy(
            update={
                "channel": Channel.USSD,
                "amount": 18_000,
                "available_balance_before": 20_000,
                "device_id": f"new-device-{index}",
                "sim_id": f"new-sim-{index}",
                "interaction_ms": 900,
                "menu_depth": 7,
                "telco_assurance": TelcoAssurance(
                    imsi_changed=True, iccid_changed=True,
                    sim_activation_age_hours=2, gateway_attested=True,
                ),
            }
        )
        decisions.append(service.score_event(attack))
    assert decisions[-1].campaign["distinct_accounts"] == 4
    assert decisions[-1].campaign["eligible"] is True
    assert decisions[-1].campaign["score"] >= 0.70


def test_consortium_requires_independent_institutions(test_settings) -> None:
    service = AtoService(test_settings)
    one = service.consortium_report(ConsortiumReportRequest(
        recipient_id="shared-mule", institution_id="bank-a", confidence=0.9
    ))
    again = service.consortium_report(ConsortiumReportRequest(
        recipient_id="shared-mule", institution_id="bank-a", confidence=0.95
    ))
    two = service.consortium_report(ConsortiumReportRequest(
        recipient_id="shared-mule", institution_id="bank-b", confidence=0.85
    ))
    assert one["score"] == 0.0 and again["independent_institutions"] == 1
    assert two["independent_institutions"] == 2 and two["score"] >= 0.85


def test_governance_appeal_privacy_succession_and_anchor(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="gov", display_name="Governance"))
    decision = service.score_event(event("gov", "gov_event", datetime.now(UTC)))
    assert service.create_appeal(decision.decision_id, AppealRequest(reason="customer disputes this intervention"))["status"] == "open"
    simulation = service.policy_simulation(PolicySimulationRequest())
    assert simulation["mutated_live_policy"] is False
    assert service.drift_report()["minimum_sample_met"] is False
    assert "protected attributes" in service.equity_report()["scope"]
    assert service.privacy_request(PrivacyRequest(account_id="gov", request_type="export", requester_id="privacy-officer"))["status"] == "queued"
    succession = service.profile_succession(ProfileSuccessionRequest(
        account_id="gov", trusted_device_confirmed=True,
        official_callback_confirmed=True, reason="verified device replacement"
    ))
    assert succession["approved"] is True
    anchor = service.audit_anchor()
    assert len(anchor["signature"]) == 64


def test_api_rbac_tenant_isolation_and_security_headers(test_settings) -> None:
    client = TestClient(create_app(test_settings))
    integration = {"X-API-Key": test_settings.api_key, "X-Tenant-ID": "demo-bank"}
    analyst = {"X-API-Key": test_settings.analyst_api_key, "X-Tenant-ID": "demo-bank"}
    auditor = {"X-API-Key": test_settings.auditor_api_key, "X-Tenant-ID": "demo-bank"}
    response = client.post("/v1/accounts", headers=integration, json={"account_id": "tenant-a", "display_name": "Tenant A"})
    assert response.status_code == 201
    assert response.headers["x-frame-options"] == "DENY"
    assert client.get("/v1/audit/verify", headers=integration).status_code == 403
    assert client.get("/v1/audit/verify", headers=auditor).status_code == 200
    assert client.get("/v1/cases", headers=analyst).status_code == 200
    other_tenant = {"X-API-Key": test_settings.api_key, "X-Tenant-ID": "partner-bank"}
    assert client.get("/v1/accounts/tenant-a/profile", headers=other_tenant).status_code == 404
    assert client.get("/v1/metrics", headers={"X-API-Key": test_settings.auditor_api_key, "X-Tenant-ID": "forbidden"}).status_code == 403


def test_feedback_dual_control_after_first_recipient_report(test_settings) -> None:
    service = AtoService(test_settings)
    now = datetime.now(UTC)
    decisions = []
    for suffix in ("a", "b"):
        account = f"dual_{suffix}"
        service.create_account(AccountCreate(account_id=account, display_name=account))
        decisions.append(service.score_event(event(account, f"dual_event_{suffix}", now, recipient="same-recipient")))
    service.add_feedback(decisions[0].decision_id, FeedbackRequest(label=FeedbackLabel.ACCOUNT_TAKEOVER, analyst_id="analyst-one"))
    with pytest.raises(ConflictError):
        service.add_feedback(decisions[1].decision_id, FeedbackRequest(label=FeedbackLabel.ACCOUNT_TAKEOVER, analyst_id="analyst-two"))
    accepted = service.add_feedback(decisions[1].decision_id, FeedbackRequest(
        label=FeedbackLabel.ACCOUNT_TAKEOVER, analyst_id="analyst-two", second_approver_id="analyst-three"
    ))
    assert accepted["recipient_reputation_update"]["distinct_accounts"] == 2


def test_psi_and_cross_tenant_direct_access(test_settings) -> None:
    assert psi([0.1] * 20, [0.1] * 20) == 0.0
    assert psi([0.1] * 20, [0.9] * 20) > 0.25
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="isolated", display_name="Isolated"), "demo-bank")
    with pytest.raises(NotFoundError):
        service.get_profile("isolated", "partner-bank")
