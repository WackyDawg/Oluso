from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from aegistwin.evaluation import (
    ablation_table,
    bootstrap_operating_point,
    detection_attribution,
    leakage_audit,
    wilson_interval,
)
from aegistwin.features import FEATURE_NAMES
from aegistwin.policy import POLICY_THRESHOLDS, risk_level_for_score
from aegistwin.schemas import AccountCreate, BehaviorEventIn, Channel, EventType, RiskLevel
from aegistwin.scoring import (
    SECURITY_FLOOR_RULES,
    AnomalyScorer,
    fuse_scores,
    fuse_scores_detailed,
    security_floors,
)
from aegistwin.service import AtoService


def feature_defaults(**overrides: float) -> dict[str, float]:
    features = {name: 0.0 for name in FEATURE_NAMES}
    features.update(history_confidence=0.8, evidence_coverage=0.8)
    features.update(overrides)
    return features


def test_security_floor_rules_have_unique_codes_and_fire_by_name() -> None:
    codes = [rule.code for rule in SECURITY_FLOOR_RULES]
    assert len(codes) == len(set(codes))

    features = feature_defaults(new_device=1.0, new_sim=1.0, balance_drain_ratio=0.5)
    fired = security_floors(features)
    assert [item["code"] for item in fired] == ["DEVICE_SIM_COCHANGE"]
    assert fired[0]["value"] == 0.775

    assert security_floors(feature_defaults()) == []


def test_detailed_fusion_matches_wrapper_and_attributes_driver() -> None:
    quiet = feature_defaults()
    breakdown = fuse_scores_detailed(0.10, 0.20, quiet)
    assert breakdown.driver == "blend"
    assert breakdown.security_floor == 0.0
    assert breakdown.model_weight == 0.58
    assert breakdown.fused_score == round(0.58 * 0.10 + 0.42 * 0.20, 6)
    assert fuse_scores(0.10, 0.20, quiet) == (breakdown.fused_score, breakdown.note)

    immature = feature_defaults(history_confidence=0.1)
    assert fuse_scores_detailed(0.10, 0.20, immature).model_weight == 0.68

    floored = feature_defaults(recovery_signal_72h=1.0, new_recipient=1.0)
    lifted = fuse_scores_detailed(0.05, 0.05, floored)
    assert lifted.driver == "security_floor"
    assert lifted.security_floor_codes == ["RECOVERY_THEN_NEW_RECIPIENT"]
    assert lifted.fused_score == 0.78
    assert lifted.blended_score < lifted.fused_score

    rules_only = fuse_scores_detailed(None, 0.3, quiet)
    assert rules_only.model_weight is None
    assert rules_only.blended_score == 0.3
    assert "unavailable" in (rules_only.note or "")


def test_policy_thresholds_are_the_single_source_of_truth() -> None:
    assert list(POLICY_THRESHOLDS) == ["monitor", "confirm", "delay", "hold"]
    assert list(POLICY_THRESHOLDS.values()) == sorted(POLICY_THRESHOLDS.values())
    assert risk_level_for_score(POLICY_THRESHOLDS["monitor"] - 0.01) == RiskLevel.LOW
    assert risk_level_for_score(POLICY_THRESHOLDS["confirm"]) == RiskLevel.ELEVATED
    assert risk_level_for_score(POLICY_THRESHOLDS["hold"]) == RiskLevel.CRITICAL


def test_wilson_and_bootstrap_intervals_bracket_the_point_estimate() -> None:
    lower, upper = wilson_interval(40, 44)
    assert lower < 40 / 44 < upper
    assert wilson_interval(0, 0) == (0.0, 0.0)

    rng = np.random.default_rng(1)
    labels = np.array([1] * 40 + [0] * 400)
    scores = np.concatenate([rng.uniform(0.4, 1.0, 40), rng.uniform(0.0, 0.6, 400)])
    result = bootstrap_operating_point(labels, scores, 0.5, resamples=200, seed=3)
    for metric in ("recall", "precision", "false_positive_rate", "roc_auc"):
        item = result["metrics"][metric]
        assert item["ci_lower"] <= item["point"] <= item["ci_upper"]
    assert result["metrics"]["recall"]["wilson"][0] < result["metrics"]["recall"]["point"]


def test_ablation_and_attribution_partition_alerts() -> None:
    scorer = AnomalyScorer()
    rows = [
        feature_defaults(recovery_signal_72h=1.0, new_recipient=1.0),  # floor-driven attack
        feature_defaults(amount_deviation=1.0, balance_drain_ratio=1.0, new_device=1.0),
        feature_defaults(),
        feature_defaults(),
    ]
    labels = np.array([1, 1, 0, 0])
    probabilities = [0.05, 0.95, 0.02, 0.01]
    breakdowns = [
        fuse_scores_detailed(probability, scorer.score(row).score, row)
        for probability, row in zip(probabilities, rows)
    ]
    threshold = POLICY_THRESHOLDS["confirm"]
    ablation = ablation_table(labels, breakdowns, threshold)
    assert set(ablation) == {
        "model_only", "anomaly_only", "blend_without_floors", "floors_only", "fused_live",
    }
    assert ablation["fused_live"]["true_positives"] == 2
    assert ablation["model_only"]["true_positives"] == 1
    assert ablation["floors_only"]["true_positives"] == 1

    attribution = detection_attribution(labels, breakdowns, threshold)
    tp = attribution["true_positives"]
    assert tp["total"] == 2
    assert tp["floor_required"] == 1
    assert tp["blend_alone"] + tp["both"] == 1
    assert attribution["floor_codes_among_true_positives"] == {"RECOVERY_THEN_NEW_RECIPIENT": 1}
    assert attribution["false_positives"]["total"] == 0


def test_leakage_audit_flags_label_proxies() -> None:
    labels = np.array([0] * 50 + [1] * 50)
    honest = np.tile([0.0, 1.0], 50)
    proxy = labels.astype(float)
    result = leakage_audit({"honest": honest, "proxy": proxy}, labels)
    assert result["passed"] is False
    assert result["features"][0]["feature"] == "proxy"
    assert result["features"][0]["separation_auc"] == 1.0
    assert leakage_audit({"honest": honest}, labels)["passed"] is True


def test_drift_report_tracks_features_actions_and_reference_window(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="drift_acct", display_name="Drift"))
    now = datetime.now(UTC)
    for index in range(24):
        service.score_event(
            BehaviorEventIn(
                event_id=f"drift_{index:03d}",
                account_id="drift_acct",
                occurred_at=now - timedelta(days=30 - index),
                event_type=EventType.PURCHASE,
                channel=Channel.APP,
                amount=1_500 + (index % 3) * 100,
                available_balance_before=20_000,
                recipient_id="merchant_known",
                device_id="device_known",
                sim_id="sim_known",
            )
        )
    report = service.drift_report()
    assert report["minimum_sample_met"] is True
    assert report["window_size"] == 12
    assert report["reference_window"]["events"] == 12
    assert report["current_window"]["events"] == 12
    assert set(report["feature_drift"]) == set(AtoService.DRIFT_MONITORED_FEATURES)
    assert all(item["status"] in {"stable", "watch", "alert"} for item in report["feature_drift"].values())
    assert report["action_drift"]["reference"]
    assert report["model_versions_in_scope"] == ["rules-only-1.0"]
    assert isinstance(report["retraining_recommended"], bool)
    assert report["reasons"]


def test_floor_driven_decision_is_labelled_in_reasons_and_snapshot(test_settings) -> None:
    service = AtoService(test_settings)
    service.create_account(AccountCreate(account_id="floor_acct", display_name="Floor"))
    now = datetime.now(UTC)
    for index in range(30):
        service.score_event(
            BehaviorEventIn(
                event_id=f"floor_base_{index:03d}",
                account_id="floor_acct",
                occurred_at=now - timedelta(days=40 - index),
                event_type=EventType.PURCHASE,
                channel=Channel.APP,
                amount=1_500,
                available_balance_before=20_000,
                recipient_id="merchant_known",
                device_id="device_known",
                sim_id="sim_known",
            )
        )
    service.score_event(
        BehaviorEventIn(
            event_id="floor_recovery",
            account_id="floor_acct",
            occurred_at=now - timedelta(minutes=30),
            event_type=EventType.ACCOUNT_RECOVERY,
            channel=Channel.APP,
            amount=0,
            device_id="device_known",
            sim_id="sim_known",
            success=True,
        )
    )
    decision = service.score_event(
        BehaviorEventIn(
            event_id="floor_attack",
            account_id="floor_acct",
            occurred_at=now,
            event_type=EventType.TRANSFER,
            channel=Channel.APP,
            amount=1_500,
            available_balance_before=20_000,
            recipient_id="never_seen_before",
            device_id="device_known",
            sim_id="sim_known",
        )
    )
    assert decision.feature_snapshot["fusion_floor_driven"] == 1.0
    assert decision.feature_snapshot["fusion_security_floor"] >= 0.78
    codes = [reason.code for reason in decision.reasons]
    assert "SECURITY_FLOOR_APPLIED" in codes
    message = next(reason.message for reason in decision.reasons if reason.code == "SECURITY_FLOOR_APPLIED")
    assert "RECOVERY_THEN_NEW_RECIPIENT" in message
