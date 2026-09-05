from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from aegistwin.api import create_app
from aegistwin.schemas import (
    AccountCreate,
    AgentTerminalAssurance,
    BehaviorEventIn,
    Channel,
    EventType,
    FeedbackLabel,
    FeedbackRequest,
    ResponseAction,
)
from aegistwin.service import AtoService


def assurance(
    terminal: str,
    *,
    attested: bool = True,
) -> AgentTerminalAssurance:
    return AgentTerminalAssurance(
        agent_token="agt_token_001",
        terminal_token=terminal,
        registered_latitude=6.5244,
        registered_longitude=3.3792,
        shift_start_hour=6,
        shift_end_hour=22,
        terminal_age_days=420,
        gateway_attested=attested,
    )


def agent_event(
    event_id: str,
    account_id: str,
    occurred_at: datetime,
    terminal: str,
    recipient: str | None,
    *,
    event_type: EventType = EventType.TRANSFER,
    attested: bool = True,
) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account_id,
        occurred_at=occurred_at,
        event_type=event_type,
        channel=Channel.AGENT,
        amount=2_000 if event_type == EventType.TRANSFER else 0,
        available_balance_before=25_000,
        recipient_id=recipient,
        device_id=f"device_{terminal}",
        ip_prefix="102.88.10.0/24",
        latitude=6.5244,
        longitude=3.3792,
        interaction_ms=25_000,
        menu_depth=6,
        navigation_signature="agent_customer_transfer",
        agent_assurance=assurance(terminal, attested=attested),
        success=event_type != EventType.FAILED_LOGIN,
    )


def create_accounts(service: AtoService, count: int) -> list[str]:
    accounts = [f"agent_customer_{index:02d}" for index in range(count)]
    for account_id in accounts:
        service.create_account(AccountCreate(account_id=account_id, display_name=account_id))
    return accounts


def test_busy_legitimate_agent_is_not_treated_as_a_mule_campaign(test_settings) -> None:
    service = AtoService(test_settings)
    accounts = create_accounts(service, 8)
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    terminal = "terminal_busy_market_001"
    decisions = []
    for index, account_id in enumerate(accounts):
        decisions.append(
            service.score_event(
                agent_event(
                    f"busy_agent_{index:02d}",
                    account_id,
                    now + timedelta(minutes=index),
                    terminal,
                    "registered_market_merchant",
                )
            )
        )
    last = decisions[-1]
    assert last.feature_snapshot["agent_customer_diversity_1h"] >= 0.60
    assert last.feature_snapshot["agent_recipient_concentration_24h"] == 1.0
    assert not any(reason.code == "AGENT_TERMINAL_CAMPAIGN" for reason in last.reasons)
    assert last.score.fused_score < 0.48
    assert last.policy.action in {ResponseAction.ALLOW, ResponseAction.ALLOW_MONITOR}


def test_compromised_terminal_campaign_crosses_accounts(test_settings) -> None:
    service = AtoService(test_settings)
    accounts = create_accounts(service, 10)
    now = datetime.now(UTC).replace(hour=14, minute=0, second=0, microsecond=0)
    terminal = "terminal_compromised_001"
    for index in range(4):
        service.score_event(
            agent_event(
                f"compromised_failed_{index}",
                accounts[index],
                now + timedelta(minutes=index),
                terminal,
                None,
                event_type=EventType.FAILED_LOGIN,
            )
        )
    for index in range(4, 9):
        service.score_event(
            agent_event(
                f"compromised_transfer_{index}",
                accounts[index],
                now + timedelta(minutes=index),
                terminal,
                "mule_agent_hub_001",
            )
        )
    decision = service.score_event(
        agent_event(
            "compromised_trigger_09",
            accounts[9],
            now + timedelta(minutes=9),
            terminal,
            "mule_agent_hub_001",
        )
    )
    assert decision.feature_snapshot["agent_customer_diversity_1h"] >= 0.80
    assert decision.feature_snapshot["agent_failed_auth_ratio_1h"] >= 0.35
    assert decision.score.fused_score >= 0.74
    assert decision.policy.requires_trusted_confirmation is True
    assert any(reason.code == "AGENT_TERMINAL_CAMPAIGN" for reason in decision.reasons)
    assert "agency terminal" in decision.customer_explanation


def test_feedback_propagates_and_unattested_claims_are_ignored(test_settings) -> None:
    service = AtoService(test_settings)
    accounts = create_accounts(service, 3)
    now = datetime.now(UTC).replace(hour=15, minute=0, second=0, microsecond=0)
    terminal = "terminal_feedback_001"
    first = service.score_event(
        agent_event("agent_feedback_source", accounts[0], now, terminal, "recipient_feedback_a")
    )
    update = service.add_feedback(
        first.decision_id,
        FeedbackRequest(
            label=FeedbackLabel.ACCOUNT_TAKEOVER,
            analyst_id="analyst_agent_1",
            notes="customer independently confirmed misuse",
        ),
    )
    assert update["agent_terminal_reputation_update"]["distinct_accounts"] == 1

    propagated = service.score_event(
        agent_event(
            "agent_feedback_propagated",
            accounts[1],
            now + timedelta(minutes=1),
            terminal,
            "recipient_feedback_b",
        )
    )
    assert propagated.agent_terminal.status == "monitor"
    assert propagated.score.fused_score >= 0.42
    assert any(reason.code == "CONFIRMED_AGENT_TERMINAL" for reason in propagated.reasons)

    forged = service.score_event(
        agent_event(
            "agent_feedback_forged",
            accounts[2],
            now + timedelta(minutes=2),
            terminal,
            "recipient_feedback_c",
            attested=False,
        )
    )
    assert forged.agent_terminal.status == "not_applicable"
    assert forged.feature_snapshot["agent_evidence_coverage"] == 0.0
    assert not any(reason.code == "CONFIRMED_AGENT_TERMINAL" for reason in forged.reasons)


def test_agent_terminal_status_requires_analyst_role(test_settings) -> None:
    client = TestClient(create_app(test_settings))
    path = "/v1/agent-terminals/terminal_status_001/status"
    integration = client.get(path, headers={"X-API-Key": test_settings.api_key})
    analyst = client.get(path, headers={"X-API-Key": test_settings.analyst_api_key})
    assert integration.status_code == 403
    assert analyst.status_code == 200
    assert analyst.json()["status"] == "clear"


def test_three_independent_confirmations_quarantine_terminal(test_settings) -> None:
    service = AtoService(test_settings)
    accounts = create_accounts(service, 4)
    now = datetime.now(UTC).replace(hour=16, minute=0, second=0, microsecond=0)
    terminal = "terminal_quarantine_001"
    for index in range(3):
        decision = service.score_event(
            agent_event(
                f"agent_quarantine_source_{index}",
                accounts[index],
                now + timedelta(minutes=index),
                terminal,
                f"agent_quarantine_recipient_{index}",
            )
        )
        request = FeedbackRequest(
            label=FeedbackLabel.ACCOUNT_TAKEOVER,
            analyst_id=f"analyst_primary_{index}",
            second_approver_id=(f"analyst_independent_{index}" if index else None),
            notes="independent customer confirmation",
        )
        update = service.add_feedback(decision.decision_id, request)
    assert update["agent_terminal_reputation_update"]["status"] == "quarantined"
    assert update["agent_terminal_reputation_update"]["distinct_accounts"] == 3

    protected = service.score_event(
        agent_event(
            "agent_quarantine_protected",
            accounts[3],
            now + timedelta(minutes=4),
            terminal,
            "agent_quarantine_new_recipient",
        )
    )
    assert protected.agent_terminal.quarantined is True
    assert protected.score.fused_score >= 0.76
    assert protected.policy.requires_trusted_confirmation is True
