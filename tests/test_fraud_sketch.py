from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from aegistwin.api import create_app
from aegistwin.fraud_sketch import sign_report, sign_revocation
from aegistwin.schemas import (
    AccountCreate,
    AgentTerminalAssurance,
    BehaviorEventIn,
    Channel,
    EventType,
    FraudSketchReportRequest,
    FraudSketchRevocationRequest,
)
from aegistwin.service import AtoService, ConflictError


def report_request(
    settings,
    institution: str,
    indicator: str,
    *,
    report_id: str,
    nonce: str,
    confidence: float = 0.90,
    observed_at: datetime | None = None,
    indicator_type: str = "recipient",
    evidence_class: str = "verified_account_takeover",
) -> FraudSketchReportRequest:
    payload = {
        "report_id": report_id,
        "institution_id": institution,
        "indicator_type": indicator_type,
        "indicator_value": indicator,
        "confidence": confidence,
        "evidence_class": evidence_class,
        "observed_at": observed_at or datetime.now(UTC),
        "ttl_hours": 168,
        "nonce": nonce,
    }
    signature = sign_report(payload, settings.fraud_sketch_institution_keys[institution])
    return FraudSketchReportRequest(**payload, signature=signature)


def seed_customer(service: AtoService, account_id: str, now: datetime) -> None:
    service.create_account(AccountCreate(account_id=account_id, display_name=account_id))
    for index in range(8):
        service.score_event(
            BehaviorEventIn(
                event_id=f"{account_id}_history_{index}",
                account_id=account_id,
                occurred_at=now - timedelta(days=8 - index),
                event_type=EventType.PURCHASE,
                channel=Channel.APP,
                amount=2_000,
                available_balance_before=100_000,
                recipient_id="ordinary-merchant",
                device_id="trusted-device",
                sim_id="trusted-sim",
                interaction_ms=8_000,
            )
        )


def transfer(
    account_id: str,
    event_id: str,
    recipient: str,
    now: datetime,
    *,
    suspicious: bool = False,
) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account_id,
        occurred_at=now,
        event_type=EventType.TRANSFER,
        channel=Channel.APP,
        amount=85_000 if suspicious else 2_500,
        available_balance_before=100_000,
        recipient_id=recipient,
        device_id="new-untrusted-device" if suspicious else "trusted-device",
        sim_id="new-untrusted-sim" if suspicious else "trusted-sim",
        interaction_ms=900 if suspicious else 8_000,
    )


def test_private_tokens_independence_and_no_raw_storage(test_settings) -> None:
    service = AtoService(test_settings)
    indicator = "sensitive-mule-account-001"
    first = service.fraud_sketch_report(
        report_request(
            test_settings,
            "bank-a",
            indicator,
            report_id="sketch-report-a-001",
            nonce="sketch-nonce-a-001",
        )
    )
    second = service.fraud_sketch_report(
        report_request(
            test_settings,
            "bank-b",
            indicator,
            report_id="sketch-report-b-001",
            nonce="sketch-nonce-b-001",
        )
    )
    assert first["status"] == "observe_only"
    assert first["independent_institutions"] == 1
    assert second["status"] == "shared_watch"
    assert second["independent_institutions"] == 2
    assert second["score"] >= 0.70
    metrics = service.database.metrics()
    assert metrics["active_fraud_sketch_reports"] == 2
    assert metrics["active_fraud_sketch_capsules"] == 1

    # closing() releases the handle; the bare connection context manager only commits.
    with closing(sqlite3.connect(test_settings.database_path)) as connection, connection:
        row = connection.execute(
            "SELECT indicator_token,institution_token FROM fraud_sketch_reports LIMIT 1"
        ).fetchone()
    assert row is not None and len(row[0]) == 64 and len(row[1]) == 64
    database_bytes = test_settings.database_path.read_bytes()
    assert indicator.encode() not in database_bytes
    assert b"bank-a" not in database_bytes


def test_signature_tamper_nonce_replay_and_unknown_institution(test_settings) -> None:
    service = AtoService(test_settings)
    valid = report_request(
        test_settings,
        "bank-a",
        "recipient-one",
        report_id="sketch-report-valid",
        nonce="sketch-nonce-shared",
    )
    tampered = valid.model_copy(update={"confidence": 0.61})
    with pytest.raises(ConflictError, match="signature"):
        service.fraud_sketch_report(tampered)
    service.fraud_sketch_report(valid)

    replay = report_request(
        test_settings,
        "bank-a",
        "recipient-two",
        report_id="sketch-report-replay",
        nonce="sketch-nonce-shared",
    )
    with pytest.raises(ConflictError, match="nonce"):
        service.fraud_sketch_report(replay)

    unknown = valid.model_copy(
        update={
            "report_id": "sketch-report-unknown",
            "institution_id": "unknown-bank",
            "nonce": "unknown-bank-nonce-1",
        }
    )
    with pytest.raises(ConflictError, match="not enrolled"):
        service.fraud_sketch_report(unknown)


def test_action_ceiling_requires_local_corroboration(test_settings) -> None:
    service = AtoService(test_settings)
    now = datetime.now(UTC)
    indicator = "shared-private-mule"
    service.fraud_sketch_report(
        report_request(
            test_settings,
            "bank-a",
            indicator,
            report_id="sketch-ceiling-a",
            nonce="sketch-ceiling-nonce-a",
        )
    )
    service.fraud_sketch_report(
        report_request(
            test_settings,
            "bank-b",
            indicator,
            report_id="sketch-ceiling-b",
            nonce="sketch-ceiling-nonce-b",
        )
    )

    seed_customer(service, "safe-sketch-customer", now)
    safe = service.score_event(
        transfer("safe-sketch-customer", "safe_sketch_event", indicator, now)
    )
    assert safe.fraud_sketch_exchange.independent_institutions == 2
    assert safe.fraud_sketch_exchange.action_ceiling == "monitor"
    assert safe.score.fused_score <= 0.42
    assert safe.policy.action.value in {"allow", "allow_with_monitoring"}

    seed_customer(service, "risky-sketch-customer", now)
    risky = service.score_event(
        transfer(
            "risky-sketch-customer",
            "risky_sketch_event",
            indicator,
            now + timedelta(seconds=1),
            suspicious=True,
        )
    )
    assert risky.fraud_sketch_exchange.local_corroboration is True
    assert risky.fraud_sketch_exchange.action_ceiling == "delay"
    assert risky.score.fused_score >= safe.score.fused_score


def test_signed_outage_cache_and_revocation(test_settings) -> None:
    service = AtoService(test_settings)
    now = datetime.now(UTC)
    indicator = "outage-shared-mule"
    for bank in ("bank-a", "bank-b"):
        service.fraud_sketch_report(
            report_request(
                test_settings,
                bank,
                indicator,
                report_id=f"outage-sketch-{bank}",
                nonce=f"outage-sketch-nonce-{bank}",
            )
        )

    service.database.set_resilience_state(
        "default",
        "degraded",
        {
            "core_banking": True,
            "telco_gateway": True,
            "consortium": False,
            "recipient_graph": True,
            "agent_integrity": True,
            "model_runtime": True,
        },
        now,
        "online",
        source_id="test-outage",
    )
    seed_customer(service, "cached-sketch-customer", now)
    cached = service.score_event(
        transfer(
            "cached-sketch-customer",
            "cached_sketch_event",
            indicator,
            now + timedelta(seconds=2),
        )
    )
    assert cached.fraud_sketch_exchange.source_mode == "signed_cache"
    assert cached.fraud_sketch_exchange.independent_institutions == 2
    assert cached.decision_confidence.level in {"low", "medium", "high"}

    payload = {
        "report_id": "outage-sketch-bank-b",
        "institution_id": "bank-b",
        "reason": "confirmed false association",
        "revoked_at": datetime.now(UTC),
        "nonce": "sketch-revocation-nonce-b",
    }
    request = FraudSketchRevocationRequest(
        **{k: v for k, v in payload.items() if k != "report_id"},
        signature=sign_revocation(
            payload, test_settings.fraud_sketch_institution_keys["bank-b"]
        ),
    )
    result = service.revoke_fraud_sketch_report("outage-sketch-bank-b", request)
    assert result["remaining_independent_institutions"] == 1
    assert result["remaining_score"] < 0.42


def test_fraud_sketch_api_is_analyst_only(test_settings) -> None:
    # Context manager runs the lifespan so pooled connections are closed with the app.
    with TestClient(create_app(test_settings)) as client:
        request = report_request(
            test_settings,
            "bank-a",
            "api-private-mule",
            report_id="api-sketch-report-001",
            nonce="api-sketch-nonce-001",
        )
        payload = request.model_dump(mode="json")
        assert client.post(
            "/v1/fraud-sketch/reports",
            headers={"X-API-Key": test_settings.api_key},
            json=payload,
        ).status_code == 403
        accepted = client.post(
            "/v1/fraud-sketch/reports",
            headers={"X-API-Key": test_settings.analyst_api_key},
            json=payload,
        )
        assert accepted.status_code == 200
        assert "indicator_token" not in accepted.json()
        assert "institution_token" not in accepted.json()


def test_attested_terminal_and_campaign_sketch_types(test_settings) -> None:
    service = AtoService(test_settings)
    now = datetime.now(UTC)
    terminal = "terminal-private-shared-001"
    for index, bank in enumerate(("bank-a", "bank-b"), start=1):
        service.fraud_sketch_report(
            report_request(
                test_settings,
                bank,
                terminal,
                report_id=f"terminal-sketch-{index}",
                nonce=f"terminal-sketch-nonce-{index}",
                indicator_type="agent_terminal",
                evidence_class="confirmed_terminal_compromise",
            )
        )
    service.create_account(AccountCreate(account_id="terminal-sketch-user", display_name="User"))
    decision = service.score_event(
        BehaviorEventIn(
            event_id="terminal_sketch_event",
            account_id="terminal-sketch-user",
            occurred_at=now + timedelta(seconds=1),
            event_type=EventType.TRANSFER,
            channel=Channel.AGENT,
            amount=4_000,
            available_balance_before=40_000,
            recipient_id="agent-merchant",
            device_id="agent-device",
            interaction_ms=6_000,
            agent_assurance=AgentTerminalAssurance(
                agent_token="agent-private-shared-001",
                terminal_token=terminal,
                gateway_attested=True,
            ),
        )
    )
    assert "agent_terminal" in decision.fraud_sketch_exchange.matched_indicators

    for index, bank in enumerate(("bank-a", "bank-b"), start=1):
        service.fraud_sketch_report(
            report_request(
                test_settings,
                bank,
                "recovery|recipient_change|sim_change",
                report_id=f"campaign-sketch-{index}",
                nonce=f"campaign-sketch-nonce-{index}",
                indicator_type="campaign",
            )
        )
    campaign = service.fraud_sketch_status(
        "campaign", "sim_change|recovery|recipient_change"
    )
    assert campaign["independent_institutions"] == 2
    assert campaign["score"] >= 0.70
