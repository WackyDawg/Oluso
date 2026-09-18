from __future__ import annotations

from oluso.features import FEATURE_NAMES
from oluso.policy import PolicyEngine
from oluso.schemas import ResponseAction


def feature_defaults() -> dict[str, float]:
    return {name: 0.0 for name in FEATURE_NAMES}


def test_policy_actions_are_reversible() -> None:
    policy = PolicyEngine()
    features = feature_defaults()
    assert policy.decide(0.10, features, regret_used=0, regret_limit=3).action == ResponseAction.ALLOW
    assert policy.decide(0.55, features, regret_used=0, regret_limit=3).action == ResponseAction.STEP_UP
    delayed = policy.decide(0.72, features, regret_used=0, regret_limit=3)
    assert delayed.action == ResponseAction.DELAY
    assert delayed.hold_seconds == 900
    held = policy.decide(0.90, features, regret_used=0, regret_limit=3)
    assert held.action == ResponseAction.HOLD
    assert held.requires_analyst_review is True


def test_regret_budget_changes_noncritical_repeated_intervention() -> None:
    policy = PolicyEngine()
    outcome = policy.decide(0.60, feature_defaults(), regret_used=3, regret_limit=3)
    assert outcome.action == ResponseAction.ALLOW_MONITOR
    assert outcome.budget_override_reason is not None


def test_security_critical_signal_overrides_regret_budget() -> None:
    features = feature_defaults()
    features.update(new_sim=1.0, new_device=1.0, balance_drain_ratio=0.90)
    outcome = PolicyEngine().decide(0.90, features, regret_used=3, regret_limit=3)
    assert outcome.action == ResponseAction.HOLD
    assert "overrides" in (outcome.budget_override_reason or "")


def test_verified_sim_change_does_not_create_critical_override() -> None:
    features = feature_defaults()
    features.update(
        new_sim=1.0,
        new_device=1.0,
        verified_sim_change=1.0,
        balance_drain_ratio=0.90,
    )
    outcome = PolicyEngine().decide(0.72, features, regret_used=3, regret_limit=3)
    assert outcome.action == ResponseAction.STEP_UP
    assert "changed a settlement delay" in (outcome.budget_override_reason or "")


def test_attested_telco_swap_signature_overrides_regret_budget() -> None:
    features = feature_defaults()
    features.update(
        new_sim=1.0,
        recent_sim_activation=0.98,
        imsi_change=1.0,
        iccid_change=1.0,
    )
    outcome = PolicyEngine().decide(0.82, features, regret_used=3, regret_limit=3)
    assert outcome.action == ResponseAction.DELAY
    assert "overrides" in (outcome.budget_override_reason or "")


def test_coercion_signature_uses_private_safety_pause() -> None:
    features = feature_defaults()
    features.update(
        new_recipient=1.0,
        call_transfer_overlap=1.0,
        screen_sharing_signal=1.0,
        coercion_evidence_coverage=1.0,
    )
    outcome = PolicyEngine().decide(0.70, features, regret_used=0, regret_limit=3)
    assert outcome.action == ResponseAction.SAFE_PAUSE
    assert outcome.hold_seconds == 900
    assert outcome.requires_trusted_confirmation is True


def test_policy_returns_personalised_costs_and_avoids_low_confidence_hold() -> None:
    features = feature_defaults()
    outcome = PolicyEngine().decide(
        0.86,
        features,
        regret_used=0,
        regret_limit=3,
        amount=25_000,
        decision_confidence=0.30,
    )
    assert outcome.action == ResponseAction.DELAY
    assert outcome.selected_expected_cost == outcome.action_costs[outcome.action.value]
    assert any("confidence" in reason.lower() for reason in outcome.personalization_reasons)
