from __future__ import annotations

import hashlib
import hmac
import math
from datetime import UTC, datetime
from typing import Any

from .storage import canonical_json

MATERIAL_STAGES = {"recovery", "new_channel", "recipient_change", "cashout", "sim_change", "identity_cochange"}


def hmac_token(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.strip().lower().encode(), hashlib.sha256).hexdigest()


def evidence_provenance(
    event: dict[str, Any], features: dict[str, float], *, model_version: str,
    policy_version: str, cutoff_at: datetime,
) -> dict[str, Any]:
    event_digest = hashlib.sha256(canonical_json(event).encode()).hexdigest()
    feature_digest = hashlib.sha256(canonical_json(features).encode()).hexdigest()
    replay_material = {
        "event_digest": event_digest,
        "feature_digest": feature_digest,
        "model_version": model_version,
        "policy_version": policy_version,
        "cutoff_at": cutoff_at.astimezone(UTC).isoformat(),
    }
    return {
        **replay_material,
        "replay_digest": hashlib.sha256(canonical_json(replay_material).encode()).hexdigest(),
    }


def campaign_signature(event: dict[str, Any], features: dict[str, float]) -> tuple[str, list[str]]:
    stages: list[str] = []
    event_type = str(event.get("event_type", ""))
    if event_type in {"account_recovery", "pin_reset"}:
        stages.append("recovery")
    if max(features.get("channel_transition_novelty", 0.0), features.get("new_channel", 0.0)) >= 0.45:
        stages.append("new_channel")
    if features.get("new_recipient", 0.0) >= 0.8:
        stages.append("recipient_change")
    if event_type in {"withdrawal", "transfer"} and features.get("balance_drain_ratio", 0.0) >= 0.5:
        stages.append("cashout")
    if max(features.get("imsi_change", 0.0), features.get("iccid_change", 0.0), features.get("recent_sim_activation", 0.0)) >= 0.5:
        stages.append("sim_change")
    if features.get("new_device", 0.0) >= 0.8 and features.get("new_sim", 0.0) >= 0.8:
        stages.append("identity_cochange")
    if features.get("interaction_speed_deviation", 0.0) >= 0.65:
        stages.append("fast_interaction")
    if not stages:
        stages.append("ordinary")
    # The signature contains attack mechanics, not raw account/device/recipient identifiers.
    signature = hashlib.sha256("|".join(sorted(stages)).encode()).hexdigest()[:20]
    return signature, sorted(stages)


def campaign_is_eligible(stages: list[str]) -> bool:
    return len(set(stages)) >= 3 and bool(MATERIAL_STAGES.intersection(stages))


def campaign_score(distinct_accounts: int, stages: list[str]) -> float:
    if not campaign_is_eligible(stages):
        return 0.0
    return round(min(0.92, 0.28 + 0.13 * distinct_accounts + 0.07 * len(set(stages))), 6)


ALLOWED_LIFECYCLE_TRANSITIONS = {
    "created": {"authorized", "held", "cancelled"},
    "authorized": {"held", "settled", "cancelled"},
    "held": {"released", "cancelled"},
    "released": {"settled", "cancelled"},
    "settled": set(),
    "cancelled": set(),
}


def validate_lifecycle_transition(current: str, target: str) -> None:
    if target not in ALLOWED_LIFECYCLE_TRANSITIONS.get(current, set()):
        raise ValueError(f"invalid lifecycle transition: {current} -> {target}")


def psi(expected: list[float], actual: list[float], bins: int = 10) -> float:
    if not expected or not actual:
        return 0.0
    lo, hi = min(expected + actual), max(expected + actual)
    if math.isclose(lo, hi):
        return 0.0
    width = (hi - lo) / bins
    total = 0.0
    for index in range(bins):
        left, right = lo + index * width, lo + (index + 1) * width
        exp = sum(left <= value < right or (index == bins - 1 and value == right) for value in expected)
        act = sum(left <= value < right or (index == bins - 1 and value == right) for value in actual)
        exp_pct = max(exp / len(expected), 1e-6)
        act_pct = max(act / len(actual), 1e-6)
        total += (act_pct - exp_pct) * math.log(act_pct / exp_pct)
    return round(total, 6)


def review_priority(risk: float, amount: float, confidence: float, reports: int) -> float:
    value = min(amount / 500_000.0, 1.0)
    return round(min(1.0, 0.55 * risk + 0.2 * value + 0.15 * (1 - confidence) + 0.1 * min(reports, 3) / 3), 6)
