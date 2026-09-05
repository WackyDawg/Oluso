from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aegistwin.features import FEATURE_NAMES
from aegistwin.network import RecipientNetworkTracker, summarize_recipient_network
from aegistwin.scoring import AnomalyScorer, fuse_scores


def transfer(event_id: str, sender: str, recipient: str, amount: float, when: datetime) -> dict:
    return {
        "event_id": event_id,
        "account_id": sender,
        "occurred_at": when.isoformat(),
        "event_type": "transfer",
        "recipient_id": recipient,
        "amount": amount,
        "success": True,
    }


def test_mule_network_distinguishes_fan_in_and_rapid_cashout() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    events = [
        transfer(f"feed_{index}", f"sender_{index}", "mule_1", 50_000, now - timedelta(minutes=50 - index))
        for index in range(6)
    ]
    events.append(transfer("cashout", "mule_1", "cashout_agent", 250_000, now - timedelta(minutes=5)))
    summary = summarize_recipient_network(events, "mule_1", "current_sender", now)
    assert summary["unique_senders_24h"] == 7
    assert summary["first_time_sender_ratio_24h"] == 1.0
    assert summary["rapid_cashout_ratio_1h"] > 0.80

    features = {name: 0.0 for name in FEATURE_NAMES}
    features.update(
        history_confidence=0.9,
        evidence_coverage=0.8,
        recipient_sender_diversity_24h=summary["unique_senders_24h"] / 12,
        recipient_first_time_sender_ratio_24h=summary["first_time_sender_ratio_24h"],
        recipient_rapid_cashout_ratio_1h=summary["rapid_cashout_ratio_1h"],
        recipient_network_coverage=1.0,
    )
    anomaly = AnomalyScorer().score(features)
    fused, _ = fuse_scores(None, anomaly.score, features)
    assert any(reason["code"] == "MULE_COLLECTION_SIGNATURE" for reason in anomaly.reasons)
    assert fused >= 0.76


def test_popular_merchant_fan_in_without_cashout_is_not_mule_signature() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    events = [
        transfer(f"merchant_{index}", f"customer_{index}", "airtime_merchant", 90_000, now - timedelta(minutes=index))
        for index in range(9)
    ]
    summary = summarize_recipient_network(events, "airtime_merchant", "current_customer", now)
    features = {name: 0.0 for name in FEATURE_NAMES}
    features.update(
        history_confidence=0.9,
        evidence_coverage=0.8,
        recipient_sender_diversity_24h=summary["unique_senders_24h"] / 12,
        recipient_first_time_sender_ratio_24h=summary["first_time_sender_ratio_24h"],
        recipient_inflow_velocity_1h=1.0,
        recipient_rapid_cashout_ratio_1h=summary["rapid_cashout_ratio_1h"],
        recipient_network_coverage=1.0,
    )
    anomaly = AnomalyScorer().score(features)
    fused, _ = fuse_scores(None, anomaly.score, features)
    assert not any(reason["code"] == "MULE_COLLECTION_SIGNATURE" for reason in anomaly.reasons)
    assert fused < 0.76


def test_incremental_tracker_matches_batch_summary() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    events = [
        transfer("a", "sender_a", "mule_2", 10_000, now - timedelta(minutes=20)),
        transfer("b", "mule_2", "cashout_agent", 8_000, now - timedelta(minutes=5)),
    ]
    tracker = RecipientNetworkTracker()
    for event in events:
        tracker.add(event)
    assert tracker.summarize("mule_2", "sender_b", now) == summarize_recipient_network(
        events, "mule_2", "sender_b", now
    )
