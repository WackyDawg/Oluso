from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from oluso.schemas import (
    AccountCreate,
    BehaviorEventIn,
    Channel,
    CoercionSignals,
    EventType,
    FeedbackLabel,
    FeedbackRequest,
    ResponseAction,
)
from oluso.service import AtoService, ConflictError


def baseline_event(index: int, now: datetime) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=f"base_{index:04d}",
        account_id="acct_service",
        occurred_at=now - timedelta(days=35 - index),
        event_type=EventType.PURCHASE,
        channel=Channel.APP,
        amount=1800 + (index % 4) * 100,
        available_balance_before=20_000,
        recipient_id="merchant_known",
        device_id="device_known",
        sim_id="sim_known",
        ip_prefix="10.0.0.0/24",
        latitude=6.5244,
        longitude=3.3792,
        interaction_ms=20_000 + (index % 3) * 200,
        menu_depth=5,
        input_method="typed",
        keystroke_interval_ms=185 + (index % 3) * 3,
        device_tilt_variance=2.2 + (index % 3) * 0.1,
        navigation_signature="app_home_pay",
    )


def test_end_to_end_takeover_scoring(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(
        AccountCreate(account_id="acct_service", display_name="Service Test")
    )
    now = datetime.now(UTC)
    for index in range(30):
        service.score_event(baseline_event(index, now))

    attack = BehaviorEventIn(
        event_id="attack_event_001",
        account_id="acct_service",
        occurred_at=now,
        event_type=EventType.TRANSFER,
        channel=Channel.USSD,
        amount=48_000,
        available_balance_before=52_000,
        recipient_id="recipient_unknown",
        device_id="device_unknown",
        sim_id="sim_unknown",
        ip_prefix="197.1.1.0/24",
        latitude=6.5244,
        longitude=3.3792,
        interaction_ms=2_000,
        menu_depth=7,
    )
    decision = service.score_event(attack)
    assert decision.score.fused_score >= 0.70
    assert decision.policy.requires_trusted_confirmation is True
    assert decision.customer_explanation.startswith("We temporarily")
    assert decision.evidence.mode == "ussd_gateway_behaviour"
    assert decision.audit_hash != "pending"
    assert any(reason.code == "DEVICE_SIM_COCHANGE" for reason in decision.reasons)
    assert service.audit.verify()["valid"] is True

    profile = service.get_profile("acct_service")
    assert profile.history_events == 31
    assert profile.transaction_events == 30  # held events cannot teach the baseline
    assert profile.profile_confidence > 0.80

    with pytest.raises(ConflictError):
        service.score_event(attack)


def test_service_returns_private_coercion_pause_and_recourse(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="acct_service", display_name="Service Test"))
    now = datetime.now(UTC)
    for index in range(30):
        service.score_event(baseline_event(index, now))
    event = baseline_event(31, now).model_copy(
        update={
            "event_id": "coercion_service_001",
            "occurred_at": now,
            "event_type": EventType.TRANSFER,
            "recipient_id": "recipient_new",
            "amount": 8_000,
            "coercion_signals": CoercionSignals(
                active_call=True,
                screen_sharing_detected=True,
                recipient_replacements=3,
                confirmation_backtracks=4,
                amount_edits=2,
                pause_before_confirmation_ms=120_000,
                recipient_pasted_during_call=True,
                on_device_coercion_score=0.91,
                consented_device_attested=True,
            ),
        }
    )
    decision = service.score_event(event)
    assert decision.policy.action == ResponseAction.SAFE_PAUSE
    assert decision.policy.hold_seconds == 900
    assert any(reason.code == "COERCION_SESSION_SIGNATURE" for reason in decision.reasons)
    assert decision.recourse_options
    assert any(option.safe_channel == "registered device" for option in decision.recourse_options)
    stored = service.get_decisions("acct_service")[0]
    assert stored.recourse_options == decision.recourse_options


def test_feedback_grows_cross_account_recipient_watchlist(test_settings) -> None:
    service = AtoService(test_settings)
    now = datetime.now(UTC)
    for account_id in ("watch_a", "watch_b"):
        service.create_account(AccountCreate(account_id=account_id, display_name=account_id))
        for index in range(12):
            base = baseline_event(index, now).model_copy(
                update={"event_id": f"{account_id}_base_{index}", "account_id": account_id}
            )
            service.score_event(base)
    first = baseline_event(20, now).model_copy(
        update={
            "event_id": "watchlist_source",
            "account_id": "watch_a",
            "occurred_at": now,
            "event_type": EventType.TRANSFER,
            "recipient_id": "recipient_shared_bad",
            "amount": 2_000,
        }
    )
    source_decision = service.score_event(first)
    update = service.add_feedback(
        source_decision.decision_id,
        FeedbackRequest(
            label=FeedbackLabel.ACCOUNT_TAKEOVER,
            analyst_id="analyst_1",
            notes="confirmed after customer callback",
        ),
    )
    assert update["recipient_reputation_update"]["distinct_accounts"] == 1
    second = first.model_copy(
        update={
            "event_id": "watchlist_cross_account",
            "account_id": "watch_b",
            "occurred_at": now + timedelta(seconds=1),
        }
    )
    decision = service.score_event(second)
    assert decision.recipient_reputation.status == "monitor"
    assert decision.recipient_reputation.confirmed_reports == 1
    assert decision.score.fused_score >= 0.42
    assert decision.policy.action == ResponseAction.ALLOW_MONITOR
    assert any(reason.code == "CONFIRMED_RECIPIENT_REPUTATION" for reason in decision.reasons)


def test_decision_confidence_is_separate_from_risk(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="confidence_new", display_name="New"))
    decision = service.score_event(
        BehaviorEventIn(
            event_id="confidence_new_event",
            account_id="confidence_new",
            occurred_at=datetime.now(UTC),
            event_type=EventType.TRANSFER,
            channel=Channel.USSD,
            amount=500,
            recipient_id="known_shop",
        )
    )
    assert decision.decision_confidence.level == "low"
    assert decision.decision_confidence.score != decision.score.fused_score
    assert decision.decision_confidence.reasons
