from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from .schemas import EventType

TRANSACTION_TYPES = {
    EventType.TRANSFER.value,
    EventType.PAYBILL.value,
    EventType.PURCHASE.value,
    EventType.WITHDRAWAL.value,
    EventType.DEPOSIT.value,
}


def parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def robust_mad(values: list[float], center: float | None = None) -> float:
    if not values:
        return 0.0
    center = median(values) if center is None else center
    return float(median([abs(value - center) for value in values]))


def confidence_from_history(transaction_count: int) -> float:
    if transaction_count <= 0:
        return 0.0
    return min(1.0, math.log1p(transaction_count) / math.log(51))


class ProfileBuilder:
    """Builds a compact behavioural twin from trusted historical events."""

    def build(
        self,
        account_id: str,
        events: list[dict[str, Any]],
        *,
        reference_time: datetime | None = None,
        profile_version: int | None = None,
    ) -> dict[str, Any]:
        reference_time = (reference_time or datetime.now(UTC)).astimezone(UTC)
        trusted_events = [
            event
            for event in events
            if event.get("_profile_eligible", True)
            and event.get("success", True)
            and event.get("event_type")
            not in {
                EventType.FAILED_LOGIN.value,
                EventType.PIN_RESET.value,
                EventType.ACCOUNT_RECOVERY.value,
            }
        ]
        transactions = [
            event
            for event in trusted_events
            if event.get("event_type") in TRANSACTION_TYPES
        ]
        amounts = [float(event.get("amount", 0.0)) for event in transactions if float(event.get("amount", 0.0)) > 0]
        amount_median = float(median(amounts)) if amounts else 0.0
        amount_mad = robust_mad(amounts, amount_median)

        hours = Counter(parse_time(event["occurred_at"]).hour for event in transactions)
        devices = Counter(event["device_id"] for event in trusted_events if event.get("device_id"))
        sims = Counter(event["sim_id"] for event in trusted_events if event.get("sim_id"))
        recipients = Counter(event["recipient_id"] for event in transactions if event.get("recipient_id"))
        channels = Counter(event["channel"] for event in trusted_events if event.get("channel"))
        ip_prefixes = Counter(event["ip_prefix"] for event in trusted_events if event.get("ip_prefix"))
        event_types = Counter(event["event_type"] for event in events if event.get("event_type"))

        interaction_by_channel: dict[str, list[float]] = defaultdict(list)
        typing_by_channel: dict[str, list[float]] = defaultdict(list)
        tilt_by_channel: dict[str, list[float]] = defaultdict(list)
        navigation_by_channel: dict[str, Counter[str]] = defaultdict(Counter)
        input_method_by_channel: dict[str, Counter[str]] = defaultdict(Counter)
        for event in trusted_events:
            channel = event["channel"]
            interaction_ms = event.get("interaction_ms")
            menu_depth = event.get("menu_depth")
            if interaction_ms and menu_depth:
                interaction_by_channel[channel].append(float(interaction_ms) / float(menu_depth))
            if event.get("keystroke_interval_ms") is not None:
                typing_by_channel[channel].append(float(event["keystroke_interval_ms"]))
            if event.get("device_tilt_variance") is not None:
                tilt_by_channel[channel].append(float(event["device_tilt_variance"]))
            if event.get("navigation_signature"):
                navigation_by_channel[channel][event["navigation_signature"]] += 1
            input_method = event.get("input_method")
            if input_method and input_method != "unknown":
                input_method_by_channel[channel][input_method] += 1

        interaction_stats: dict[str, dict[str, float]] = {}
        for channel, values in interaction_by_channel.items():
            center = float(median(values))
            interaction_stats[channel] = {
                "median_ms_per_step": center,
                "mad_ms_per_step": robust_mad(values, center),
                "samples": float(len(values)),
            }

        def channel_stats(values_by_channel: dict[str, list[float]]) -> dict[str, dict[str, float]]:
            result: dict[str, dict[str, float]] = {}
            for channel, values in values_by_channel.items():
                center = float(median(values))
                result[channel] = {
                    "median": center,
                    "mad": robust_mad(values, center),
                    "samples": float(len(values)),
                }
            return result

        cutoff_24h = reference_time - timedelta(hours=24)
        recent_failed_auth = sum(
            1
            for event in events
            if event.get("event_type") == EventType.FAILED_LOGIN.value
            and parse_time(event["occurred_at"]) >= cutoff_24h
        )

        last_event = (
            max(trusted_events, key=lambda item: parse_time(item["occurred_at"]))
            if trusted_events
            else None
        )
        last_location_event = None
        located = [
            event
            for event in trusted_events
            if event.get("latitude") is not None and event.get("longitude") is not None
        ]
        if located:
            last_location_event = max(located, key=lambda item: parse_time(item["occurred_at"]))

        return {
            "account_id": account_id,
            "profile_version": profile_version if profile_version is not None else len(events),
            "history_events": len(events),
            "transaction_events": len(transactions),
            "profile_confidence": round(confidence_from_history(len(transactions)), 6),
            "amount_median": round(amount_median, 2),
            "amount_mad": round(amount_mad, 2),
            "common_hours": [hour for hour, _ in hours.most_common(5)],
            "hour_counts": dict(hours),
            "device_counts": dict(devices),
            "sim_counts": dict(sims),
            "recipient_counts": dict(recipients),
            "channel_counts": dict(channels),
            "ip_prefix_counts": dict(ip_prefixes),
            "event_type_counts": dict(event_types),
            "known_devices": len(devices),
            "known_sims": len(sims),
            "known_recipients": len(recipients),
            "known_channels": sorted(channels),
            "interaction_stats": interaction_stats,
            "typing_stats": channel_stats(typing_by_channel),
            "device_tilt_stats": channel_stats(tilt_by_channel),
            "navigation_counts": {
                channel: dict(counts) for channel, counts in navigation_by_channel.items()
            },
            "input_method_counts": {
                channel: dict(counts) for channel, counts in input_method_by_channel.items()
            },
            "recent_failed_auth_24h": recent_failed_auth,
            "last_event_at": last_event["occurred_at"] if last_event else None,
            "last_event_channel": last_event.get("channel") if last_event else None,
            "last_event_device": last_event.get("device_id") if last_event else None,
            "last_event_sim": last_event.get("sim_id") if last_event else None,
            "last_location": {
                "latitude": last_location_event.get("latitude"),
                "longitude": last_location_event.get("longitude"),
                "occurred_at": last_location_event.get("occurred_at"),
            }
            if last_location_event
            else None,
            "updated_at": reference_time.isoformat(),
        }
