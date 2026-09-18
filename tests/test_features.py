from __future__ import annotations

from datetime import UTC, datetime, timedelta

from oluso.features import FeatureEngine, compute_risk_window
from oluso.schemas import BehaviorEventIn, Channel, CoercionSignals, EventType, TelcoAssurance


def history_event(index: int, now: datetime) -> dict:
    return {
        "event_id": f"hist_{index:03d}",
        "account_id": "acct_test",
        "occurred_at": (now - timedelta(days=30 - index)).isoformat(),
        "event_type": "purchase",
        "channel": "app",
        "amount": 2000 + (index % 3) * 100,
        "available_balance_before": 20_000,
        "recipient_id": "merchant_known",
        "device_id": "device_known",
        "sim_id": "sim_known",
        "ip_prefix": "10.10.1.0/24",
        "latitude": 6.5244,
        "longitude": 3.3792,
        "interaction_ms": 20_000,
        "menu_depth": 5,
        "input_method": "typed",
        "keystroke_interval_ms": 185,
        "device_tilt_variance": 2.3,
        "navigation_signature": "app_home_pay",
        "success": True,
        "metadata": {},
    }


def test_feature_engine_uses_server_history() -> None:
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    history = [history_event(index, now) for index in range(30)]
    history[-1]["occurred_at"] = (now - timedelta(minutes=20)).isoformat()
    engine = FeatureEngine()
    account = {"account_id": "acct_test", "shared_device_allowed": False}

    normal = BehaviorEventIn(
        event_id="evt_normal_001",
        account_id="acct_test",
        occurred_at=now,
        event_type=EventType.PURCHASE,
        channel=Channel.APP,
        amount=2100,
        available_balance_before=20_000,
        recipient_id="merchant_known",
        device_id="device_known",
        sim_id="sim_known",
        ip_prefix="10.10.1.0/24",
        latitude=6.5244,
        longitude=3.3792,
        interaction_ms=20_500,
        menu_depth=5,
        input_method="typed",
        keystroke_interval_ms=188,
        device_tilt_variance=2.4,
        navigation_signature="app_home_pay",
    )
    normal_features, profile = engine.extract(normal, history, account)
    assert profile["transaction_events"] == 30
    assert normal_features["history_confidence"] > 0.80
    assert normal_features["new_device"] == 0
    assert normal_features["new_sim"] == 0
    assert normal_features["new_recipient"] == 0
    assert normal_features["amount_deviation"] < 0.20

    suspicious = normal.model_copy(
        update={
            "event_id": "evt_attack_001",
            "event_type": EventType.TRANSFER,
            "channel": Channel.USSD,
            "amount": 48_000,
            "available_balance_before": 52_000,
            "recipient_id": "recipient_unknown",
            "device_id": "device_unknown",
            "sim_id": "sim_unknown",
            "ip_prefix": "197.1.1.0/24",
            "latitude": 9.0765,
            "longitude": 7.3986,
            "interaction_ms": 2_000,
            "menu_depth": 7,
        }
    )
    attack_features, _ = engine.extract(suspicious, history, account)
    assert attack_features["new_device"] == 1
    assert attack_features["new_sim"] == 1
    assert attack_features["new_recipient"] == 1
    assert attack_features["amount_deviation"] > 0.90
    assert attack_features["balance_drain_ratio"] > 0.90
    assert attack_features["impossible_travel"] > 0.0
    assert attack_features["navigation_novelty"] > 0.0


def test_shared_device_setting_reduces_rule_contribution() -> None:
    from oluso.scoring import AnomalyScorer

    base = {name: 0.0 for name in __import__("oluso.features", fromlist=["FEATURE_NAMES"]).FEATURE_NAMES}
    base.update(history_confidence=1.0, new_device=1.0, device_rarity=1.0)
    scorer = AnomalyScorer()
    unshared = scorer.score(base).score
    shared = scorer.score({**base, "shared_device_allowed": 1.0}).score
    assert shared < unshared


def test_verified_sim_change_is_a_mitigation() -> None:
    from oluso.scoring import AnomalyScorer, fuse_scores

    base = {
        name: 0.0
        for name in __import__("oluso.features", fromlist=["FEATURE_NAMES"]).FEATURE_NAMES
    }
    base.update(
        history_confidence=1.0,
        new_device=1.0,
        device_rarity=1.0,
        new_sim=1.0,
        balance_drain_ratio=0.75,
        evidence_coverage=0.8,
    )
    scorer = AnomalyScorer()
    unverified = scorer.score(base).score
    unverified_fused, _ = fuse_scores(None, unverified, base)
    verified_features = {**base, "verified_sim_change": 1.0}
    verified = scorer.score(verified_features).score
    verified_fused, _ = fuse_scores(None, verified, verified_features)
    assert verified < unverified
    assert verified_fused < unverified_fused


def test_only_attested_telco_lifecycle_can_raise_risk() -> None:
    now = datetime(2026, 8, 23, 12, tzinfo=UTC)
    history = [history_event(index, now) for index in range(30)]
    engine = FeatureEngine()
    account = {"account_id": "acct_test", "shared_device_allowed": False}
    payload = {
        "event_id": "evt_telco_001",
        "account_id": "acct_test",
        "occurred_at": now,
        "event_type": EventType.TRANSFER,
        "channel": Channel.USSD,
        "amount": 8_000,
        "available_balance_before": 25_000,
        "recipient_id": "merchant_known",
        "sim_id": "sim_changed",
        "interaction_ms": 12_000,
        "menu_depth": 5,
        "telco_assurance": TelcoAssurance(
            imsi_changed=True,
            iccid_changed=True,
            sim_activation_age_hours=1,
            otp_to_sim_change_minutes=10,
            otp_sim_geo_distance_km=500,
            gateway_attested=False,
        ),
    }
    untrusted, _ = engine.extract(BehaviorEventIn(**payload), history, account)
    payload["telco_assurance"] = payload["telco_assurance"].model_copy(
        update={"gateway_attested": True}
    )
    trusted, _ = engine.extract(BehaviorEventIn(**payload), history, account)
    assert untrusted["telco_assurance_coverage"] == 0
    assert untrusted["imsi_change"] == 0
    assert trusted["telco_assurance_coverage"] > 0.5
    assert trusted["recent_sim_activation"] > 0.9
    assert trusted["otp_sim_geo_mismatch"] == 1.0


def test_attested_sim_swap_has_security_floor_but_verified_change_does_not() -> None:
    from oluso.scoring import AnomalyScorer, fuse_scores

    features = {
        name: 0.0
        for name in __import__("oluso.features", fromlist=["FEATURE_NAMES"]).FEATURE_NAMES
    }
    features.update(
        history_confidence=0.8,
        evidence_coverage=0.8,
        new_sim=1.0,
        recent_sim_activation=0.99,
        imsi_change=1.0,
        iccid_change=1.0,
        otp_sim_change_proximity=0.95,
        otp_sim_geo_mismatch=1.0,
    )
    anomaly = AnomalyScorer().score(features)
    unverified, _ = fuse_scores(None, anomaly.score, features)
    verified_features = {**features, "verified_sim_change": 1.0}
    verified_anomaly = AnomalyScorer().score(verified_features)
    verified, _ = fuse_scores(None, verified_anomaly.score, verified_features)
    assert unverified >= 0.84
    assert verified < 0.48


def test_risk_window_decays_and_expires() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    history = [
        {
            "event_id": "recovery_1",
            "account_id": "acct_test",
            "occurred_at": (now - timedelta(minutes=30)).isoformat(),
            "event_type": "account_recovery",
        }
    ]
    current = compute_risk_window(history, now)
    later = compute_risk_window(history, now + timedelta(hours=48))
    expired = compute_risk_window(history, now + timedelta(hours=73))
    assert current["state"] == "elevated"
    assert current["score"] > later["score"] > 0
    assert expired["state"] == "clear"
    assert expired["score"] == 0


def test_coercion_telemetry_requires_consent_and_attestation() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    history = [history_event(index, now) for index in range(30)]
    engine = FeatureEngine()
    account = {"account_id": "acct_test", "shared_device_allowed": False}
    base = BehaviorEventIn(
        event_id="coercion_1",
        account_id="acct_test",
        occurred_at=now,
        event_type=EventType.TRANSFER,
        channel=Channel.APP,
        amount=8_000,
        available_balance_before=30_000,
        recipient_id="new_recipient",
        device_id="device_known",
        sim_id="sim_known",
        input_method="typed",
        interaction_ms=80_000,
        menu_depth=5,
        coercion_signals=CoercionSignals(
            active_call=True,
            screen_sharing_detected=True,
            recipient_replacements=3,
            confirmation_backtracks=4,
            recipient_pasted_during_call=True,
            on_device_coercion_score=0.92,
            consented_device_attested=False,
        ),
    )
    untrusted, _ = engine.extract(base, history, account)
    trusted, _ = engine.extract(
        base.model_copy(
            update={
                "event_id": "coercion_2",
                "coercion_signals": base.coercion_signals.model_copy(
                    update={"consented_device_attested": True}
                ),
            }
        ),
        history,
        account,
    )
    assert untrusted["coercion_evidence_coverage"] == 0
    assert untrusted["call_transfer_overlap"] == 0
    assert trusted["coercion_evidence_coverage"] >= 0.85
    assert trusted["call_transfer_overlap"] == 1
    assert trusted["confirmation_friction"] == 1


def test_cross_channel_sequence_is_scored_as_one_story() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    history = [history_event(index, now) for index in range(30)]
    for item in history:
        item["channel"] = "ussd"
        item["device_id"] = "feature_phone_known"
    history.append(
        {
            **history_event(99, now),
            "event_id": "new_app_login",
            "occurred_at": (now - timedelta(minutes=8)).isoformat(),
            "event_type": "login",
            "channel": "app",
            "amount": 0,
            "device_id": "attacker_app_device",
        }
    )
    event = BehaviorEventIn(
        event_id="cross_channel_001",
        account_id="acct_test",
        occurred_at=now,
        event_type=EventType.TRANSFER,
        channel=Channel.USSD,
        amount=6_000,
        available_balance_before=20_000,
        recipient_id="new_recipient",
        device_id="feature_phone_known",
        sim_id="sim_known",
        interaction_ms=16_000,
        menu_depth=5,
    )
    features, _ = FeatureEngine().extract(
        event, history, {"account_id": "acct_test", "shared_device_allowed": False}
    )
    assert features["new_channel_enrollment_24h"] == 1
    assert features["app_to_ussd_handoff"] == 1
    assert features["channel_transition_novelty"] > 0.90


def test_calendar_twin_recognises_three_month_pattern() -> None:
    now = datetime(2026, 8, 25, 12, tzinfo=UTC)
    history = [history_event(index, now) for index in range(12)]
    for index, days in enumerate((92, 61, 31)):
        history.append(
            {
                **history_event(70 + index, now),
                "occurred_at": (now - timedelta(days=days)).isoformat(),
                "event_type": "transfer",
                "amount": 20_000,
                "recipient_id": "landlord_recurring",
            }
        )
    event = BehaviorEventIn(
        event_id="calendar_001",
        account_id="acct_test",
        occurred_at=now,
        event_type=EventType.TRANSFER,
        channel=Channel.APP,
        amount=20_500,
        available_balance_before=80_000,
        recipient_id="landlord_recurring",
        device_id="device_known",
        sim_id="sim_known",
        interaction_ms=20_000,
        menu_depth=5,
    )
    features, _ = FeatureEngine().extract(
        event, history, {"account_id": "acct_test", "shared_device_allowed": False}
    )
    assert features["calendar_confidence"] >= 0.75
    assert features["recurring_payment_match"] == 1.0
