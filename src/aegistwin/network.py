from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from .profile import TRANSACTION_TYPES, parse_time


def summarize_recipient_network(
    events: list[dict[str, Any]],
    recipient_id: str | None,
    current_sender: str,
    reference_time: datetime,
) -> dict[str, float]:
    """Build causal recipient-keyed graph aggregates from events strictly before this event."""

    empty = {
        "unique_senders_24h": 0.0,
        "first_time_sender_ratio_24h": 0.0,
        "inflow_amount_1h": 0.0,
        "outflow_amount_1h": 0.0,
        "rapid_cashout_ratio_1h": 0.0,
        "current_sender_first_time": 0.0,
        "network_evidence_available": 0.0,
    }
    if not recipient_id:
        return empty

    reference = reference_time.astimezone(UTC)
    prior = [item for item in events if parse_time(item["occurred_at"]) < reference]
    incoming_all = [
        item
        for item in prior
        if item.get("event_type") in TRANSACTION_TYPES
        and item.get("recipient_id") == recipient_id
        and bool(item.get("success", True))
    ]
    cutoff_24h = reference - timedelta(hours=24)
    cutoff_1h = reference - timedelta(hours=1)
    incoming_24h = [item for item in incoming_all if parse_time(item["occurred_at"]) >= cutoff_24h]
    incoming_1h = [item for item in incoming_all if parse_time(item["occurred_at"]) >= cutoff_1h]
    sender_counts = Counter(str(item.get("account_id")) for item in incoming_all)
    senders_24h = {str(item.get("account_id")) for item in incoming_24h}
    current_first = current_sender not in sender_counts
    senders_with_current = set(senders_24h)
    senders_with_current.add(current_sender)
    first_time_senders = sum(sender_counts[sender] <= 1 for sender in senders_24h)
    if current_first:
        first_time_senders += 1

    outgoing_1h = [
        item
        for item in prior
        if item.get("event_type") in TRANSACTION_TYPES
        and item.get("account_id") == recipient_id
        and parse_time(item["occurred_at"]) >= cutoff_1h
        and bool(item.get("success", True))
    ]
    inflow = sum(float(item.get("amount", 0.0)) for item in incoming_1h)
    outflow = sum(float(item.get("amount", 0.0)) for item in outgoing_1h)
    return {
        "unique_senders_24h": float(len(senders_with_current)),
        "first_time_sender_ratio_24h": first_time_senders / max(1, len(senders_with_current)),
        "inflow_amount_1h": inflow,
        "outflow_amount_1h": outflow,
        "rapid_cashout_ratio_1h": min(1.0, outflow / max(1.0, inflow)),
        "current_sender_first_time": 1.0 if current_first else 0.0,
        "network_evidence_available": 1.0,
    }


class RecipientNetworkTracker:
    """Incremental index used by simulation so graph features remain inexpensive."""

    def __init__(self) -> None:
        self._incoming: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(self, event: dict[str, Any]) -> None:
        sender = str(event.get("account_id") or "")
        recipient = event.get("recipient_id")
        if recipient:
            self._incoming[str(recipient)].append(event)
        if sender:
            self._outgoing[sender].append(event)

    def summarize(
        self,
        recipient_id: str | None,
        current_sender: str,
        reference_time: datetime,
    ) -> dict[str, float]:
        if not recipient_id:
            return summarize_recipient_network([], None, current_sender, reference_time)
        relevant = [
            *self._incoming.get(recipient_id, []),
            *self._outgoing.get(recipient_id, []),
        ]
        return summarize_recipient_network(relevant, recipient_id, current_sender, reference_time)
