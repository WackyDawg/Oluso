from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, timedelta
from typing import Any

from .profile import TRANSACTION_TYPES, parse_time
from .schemas import BehaviorEventIn, Channel, EventType


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0.0, 1 - value)))


def empty_agent_context() -> dict[str, float]:
    return {
        "customer_diversity_1h": 0.0,
        "recipient_concentration_24h": 0.0,
        "first_time_recipient_ratio_24h": 0.0,
        "failed_auth_ratio_1h": 0.0,
        "value_velocity_1h": 0.0,
        "location_mismatch": 0.0,
        "after_hours": 0.0,
        "terminal_novelty": 0.0,
        "confirmed_fraud_score": 0.0,
        "confirmed_distinct_accounts": 0.0,
        "evidence_available": 0.0,
    }


def summarize_agent_terminal(
    events: list[dict[str, Any]],
    event: BehaviorEventIn,
    reputation: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Create causal, cross-customer agent-terminal aggregates from attested events."""

    assurance = event.agent_assurance
    if (
        event.channel != Channel.AGENT
        or assurance is None
        or not assurance.gateway_attested
    ):
        return empty_agent_context()

    reference = event.occurred_at.astimezone(UTC)
    prior = [item for item in events if parse_time(item["occurred_at"]) < reference]
    terminal_events: list[dict[str, Any]] = []
    for item in prior:
        item_assurance = item.get("agent_assurance") or {}
        if (
            item.get("channel") == Channel.AGENT.value
            and isinstance(item_assurance, dict)
            and item_assurance.get("gateway_attested")
            and item_assurance.get("terminal_token") == assurance.terminal_token
        ):
            terminal_events.append(item)

    cutoff_1h = reference - timedelta(hours=1)
    cutoff_24h = reference - timedelta(hours=24)
    recent_1h = [item for item in terminal_events if parse_time(item["occurred_at"]) >= cutoff_1h]
    recent_24h = [item for item in terminal_events if parse_time(item["occurred_at"]) >= cutoff_24h]
    current = event.model_dump(mode="json")
    recent_1h_with_current = [*recent_1h, current]
    recent_24h_with_current = [*recent_24h, current]

    customers = {str(item.get("account_id")) for item in recent_1h_with_current}
    transactions_24h = [
        item
        for item in recent_24h_with_current
        if item.get("event_type") in TRANSACTION_TYPES and item.get("recipient_id")
    ]
    recipient_counts = Counter(str(item["recipient_id"]) for item in transactions_24h)
    concentration = max(recipient_counts.values(), default=0) / max(1, len(transactions_24h))

    global_pairs = Counter(
        (str(item.get("account_id")), str(item.get("recipient_id")))
        for item in prior
        if item.get("event_type") in TRANSACTION_TYPES and item.get("recipient_id")
    )
    first_time = sum(
        global_pairs[(str(item.get("account_id")), str(item.get("recipient_id")))] == 0
        for item in transactions_24h
    )
    failed = sum(
        item.get("event_type") == EventType.FAILED_LOGIN.value for item in recent_1h_with_current
    )
    value_1h = sum(
        float(item.get("amount", 0.0))
        for item in recent_1h_with_current
        if item.get("event_type") in TRANSACTION_TYPES
    )

    location_mismatch = 0.0
    if (
        assurance.registered_latitude is not None
        and assurance.registered_longitude is not None
        and event.latitude is not None
        and event.longitude is not None
    ):
        distance = _haversine_km(
            assurance.registered_latitude,
            assurance.registered_longitude,
            event.latitude,
            event.longitude,
        )
        location_mismatch = _clamp((distance - 10.0) / 90.0)

    after_hours = 0.0
    if assurance.shift_start_hour is not None and assurance.shift_end_hour is not None:
        hour = reference.hour
        start = assurance.shift_start_hour
        end = assurance.shift_end_hour
        inside = start <= hour < end if start < end else hour >= start or hour < end
        after_hours = 0.0 if inside else 1.0

    reputation = reputation or {}
    provided_fields = [
        assurance.registered_latitude,
        assurance.registered_longitude,
        assurance.shift_start_hour,
        assurance.shift_end_hour,
        assurance.terminal_age_days,
    ]
    return {
        "customer_diversity_1h": float(len(customers)),
        "recipient_concentration_24h": concentration,
        "first_time_recipient_ratio_24h": first_time / max(1, len(transactions_24h)),
        "failed_auth_ratio_1h": failed / max(1, len(recent_1h_with_current)),
        "value_velocity_1h": value_1h,
        "location_mismatch": location_mismatch,
        "after_hours": after_hours,
        "terminal_novelty": (
            _clamp(1.0 - assurance.terminal_age_days / 30.0)
            if assurance.terminal_age_days is not None
            else 0.0
        ),
        "confirmed_fraud_score": float(reputation.get("score", 0.0)),
        "confirmed_distinct_accounts": float(reputation.get("distinct_accounts", 0.0)),
        "evidence_available": (3 + sum(value is not None for value in provided_fields)) / 8.0,
    }


class AgentTerminalTracker:
    """Incremental terminal index used by the synthetic generator."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(self, event: dict[str, Any]) -> None:
        assurance = event.get("agent_assurance") or {}
        if (
            event.get("channel") == Channel.AGENT.value
            and isinstance(assurance, dict)
            and assurance.get("gateway_attested")
            and assurance.get("terminal_token")
        ):
            self._events[str(assurance["terminal_token"])].append(event)

    def summarize(
        self,
        event: BehaviorEventIn,
        reputation: dict[str, Any] | None = None,
    ) -> dict[str, float]:
        assurance = event.agent_assurance
        relevant = self._events.get(assurance.terminal_token, []) if assurance else []
        return summarize_agent_terminal(relevant, event, reputation)
