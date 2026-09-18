from __future__ import annotations

import math
from datetime import UTC, timedelta
from itertools import pairwise
from typing import Any

from .profile import TRANSACTION_TYPES, ProfileBuilder, parse_time
from .schemas import BehaviorEventIn, Channel, EventType, InputMethod

FEATURE_NAMES = [
    "amount_deviation",
    "amount_to_median",
    "balance_drain_ratio",
    "unusual_hour",
    "new_recipient",
    "recipient_rarity",
    "recipient_sender_diversity_24h",
    "recipient_first_time_sender_ratio_24h",
    "recipient_inflow_velocity_1h",
    "recipient_rapid_cashout_ratio_1h",
    "recipient_network_coverage",
    "recipient_confirmed_fraud_score",
    "recipient_confirmed_accounts",
    "recipient_watchlist_coverage",
    "new_device",
    "device_rarity",
    "new_sim",
    "new_ip_prefix",
    "new_channel",
    "channel_transition_novelty",
    "cross_channel_events_15m",
    "new_channel_enrollment_24h",
    "app_to_ussd_handoff",
    "cross_channel_device_mismatch",
    "velocity_5m",
    "velocity_1h",
    "failed_auth_24h",
    "recovery_signal_72h",
    "account_hazard_score",
    "risk_window_hours_remaining",
    "impossible_travel",
    "interaction_speed_deviation",
    "typing_cadence_deviation",
    "paste_anomaly",
    "device_handling_deviation",
    "navigation_novelty",
    "day_of_month_deviation",
    "recurring_payment_match",
    "calendar_confidence",
    "call_transfer_overlap",
    "screen_sharing_signal",
    "recipient_edit_anomaly",
    "confirmation_friction",
    "coercion_on_device_score",
    "coercion_evidence_coverage",
    "verified_sim_change",
    "recent_sim_activation",
    "repeat_sim_change",
    "imsi_change",
    "iccid_change",
    "sim_type_change",
    "otp_sim_change_proximity",
    "otp_sim_geo_mismatch",
    "short_previous_sim_tenure",
    "telco_assurance_coverage",
    "evidence_coverage",
    "history_confidence",
    "shared_device_allowed",
    "is_ussd",
    "is_transfer",
    "is_withdrawal",
]

# Confirmed-reputation fields are delayed operational intelligence, not population-model
# training inputs. Event-type flags are also excluded so the model cannot learn the
# synthetic shortcut that attacks are transfers while much normal traffic is not.
MODEL_EXCLUDED_FEATURES = {
    "recipient_confirmed_fraud_score",
    "recipient_confirmed_accounts",
    "recipient_watchlist_coverage",
    "is_transfer",
    "is_withdrawal",
}
MODEL_FEATURE_NAMES = [
    name for name in FEATURE_NAMES if name not in MODEL_EXCLUDED_FEATURES
]

# These features belong to the transparent Agent-Terminal Integrity Twin. They are
# intentionally kept outside the frozen population-model schema so the existing
# model remains reproducible while the new cross-customer lens is evaluated openly.
AGENT_FEATURE_NAMES = [
    "is_agent",
    "agent_customer_diversity_1h",
    "agent_recipient_concentration_24h",
    "agent_first_time_recipient_ratio_24h",
    "agent_failed_auth_ratio_1h",
    "agent_value_velocity_1h",
    "agent_location_mismatch",
    "agent_after_hours",
    "agent_terminal_novelty",
    "agent_confirmed_fraud_score",
    "agent_confirmed_accounts",
    "agent_evidence_coverage",
]


def clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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


def compute_risk_window(
    history: list[dict[str, Any]], reference_time: Any
) -> dict[str, Any]:
    """Create a decaying precursor-hazard state without needing a survival-model service."""

    reference = reference_time.astimezone(UTC)
    contributions: list[tuple[str, float, float]] = []
    for item in history:
        age_hours = max(0.0, (reference - parse_time(item["occurred_at"])).total_seconds() / 3600)
        event_type = item.get("event_type")
        if event_type == EventType.FAILED_LOGIN.value and age_hours <= 24:
            contributions.append(("failed authentication", 0.08 * math.exp(-age_hours / 12), 24 - age_hours))
        elif event_type == EventType.ACCOUNT_RECOVERY.value and age_hours <= 72:
            contributions.append(("account recovery", 0.35 * math.exp(-age_hours / 36), 72 - age_hours))
        elif event_type == EventType.PIN_RESET.value and age_hours <= 48:
            contributions.append(("PIN reset", 0.25 * math.exp(-age_hours / 24), 48 - age_hours))
        telco = item.get("telco_assurance") or {}
        if (
            isinstance(telco, dict)
            and telco.get("gateway_attested")
            and not item.get("sim_change_verified")
            and (telco.get("imsi_changed") or telco.get("iccid_changed"))
            and age_hours <= 48
        ):
            contributions.append(("unverified SIM identity change", 0.40 * math.exp(-age_hours / 24), 48 - age_hours))
    score = clamp(sum(item[1] for item in contributions))
    active = sorted({item[0] for item in contributions})
    return {
        "state": "high" if score >= 0.60 else "elevated" if score >= 0.30 else "watch" if score > 0 else "clear",
        "score": round(score, 6),
        "hours_remaining": round(max((item[2] for item in contributions), default=0.0), 2),
        "active_precursors": active,
    }


class FeatureEngine:
    def __init__(self) -> None:
        self.profile_builder = ProfileBuilder()

    def extract(
        self,
        event: BehaviorEventIn,
        history: list[dict[str, Any]],
        account: dict[str, Any],
        recipient_context: dict[str, float] | None = None,
        agent_context: dict[str, float] | None = None,
    ) -> tuple[dict[str, float], dict[str, Any]]:
        occurred_at = event.occurred_at.astimezone(UTC)
        profile = self.profile_builder.build(
            event.account_id,
            history,
            reference_time=occurred_at,
            profile_version=len(history),
        )
        confidence = float(profile["profile_confidence"])
        amount_median = float(profile["amount_median"])
        amount_mad = float(profile["amount_mad"])

        if event.amount > 0 and amount_median > 0:
            scale = max(1.4826 * amount_mad, amount_median * 0.08, 50.0)
            amount_z = abs(event.amount - amount_median) / scale
            amount_deviation = clamp(amount_z / 6.0)
            amount_to_median = clamp(event.amount / max(amount_median, 1.0) / 8.0)
        else:
            amount_deviation = 0.0
            amount_to_median = 0.0

        if event.available_balance_before and event.available_balance_before > 0:
            balance_drain_ratio = clamp(event.amount / event.available_balance_before)
        else:
            balance_drain_ratio = 0.0

        common_hours = profile["common_hours"]
        if common_hours and confidence > 0:
            hour = occurred_at.hour
            nearest = min(min(abs(hour - known), 24 - abs(hour - known)) for known in common_hours)
            unusual_hour = clamp(nearest / 8.0)
        else:
            unusual_hour = 0.25

        recipient_counts = profile["recipient_counts"]
        recipient_seen = int(recipient_counts.get(event.recipient_id, 0)) if event.recipient_id else 0
        total_recipient_events = max(1, sum(int(value) for value in recipient_counts.values()))
        new_recipient = 1.0 if event.recipient_id and recipient_seen == 0 else 0.0
        recipient_rarity = (
            clamp(1.0 - recipient_seen / total_recipient_events) if event.recipient_id else 0.0
        )
        recipient_context = recipient_context or {}
        agent_context = agent_context or {}
        recipient_sender_diversity = clamp(
            recipient_context.get("unique_senders_24h", 0.0) / 12.0
        )
        recipient_first_time_ratio = clamp(
            recipient_context.get("first_time_sender_ratio_24h", 0.0)
        )
        recipient_inflow_velocity = clamp(
            (recipient_context.get("inflow_amount_1h", 0.0) + event.amount) / 500_000.0
        )
        recipient_rapid_cashout = clamp(
            recipient_context.get("rapid_cashout_ratio_1h", 0.0)
        )
        recipient_network_coverage = clamp(
            recipient_context.get("network_evidence_available", 0.0)
        )
        recipient_confirmed_fraud_score = clamp(
            recipient_context.get("confirmed_fraud_score", 0.0)
        )
        recipient_confirmed_accounts = clamp(
            recipient_context.get("confirmed_distinct_accounts", 0.0) / 3.0
        )
        recipient_watchlist_coverage = clamp(
            recipient_context.get("watchlist_evidence_available", 0.0)
        )
        agent_customer_diversity = clamp(agent_context.get("customer_diversity_1h", 0.0) / 12.0)
        agent_recipient_concentration = clamp(
            agent_context.get("recipient_concentration_24h", 0.0)
        )
        agent_first_time_recipient_ratio = clamp(
            agent_context.get("first_time_recipient_ratio_24h", 0.0)
        )
        agent_failed_auth_ratio = clamp(agent_context.get("failed_auth_ratio_1h", 0.0))
        agent_value_velocity = clamp(agent_context.get("value_velocity_1h", 0.0) / 1_000_000.0)
        agent_location_mismatch = clamp(agent_context.get("location_mismatch", 0.0))
        agent_after_hours = clamp(agent_context.get("after_hours", 0.0))
        agent_terminal_novelty = clamp(agent_context.get("terminal_novelty", 0.0))
        agent_confirmed_fraud_score = clamp(agent_context.get("confirmed_fraud_score", 0.0))
        agent_confirmed_accounts = clamp(
            agent_context.get("confirmed_distinct_accounts", 0.0) / 3.0
        )
        agent_evidence_coverage = clamp(agent_context.get("evidence_available", 0.0))

        device_counts = profile["device_counts"]
        device_seen = int(device_counts.get(event.device_id, 0)) if event.device_id else 0
        total_device_events = max(1, sum(int(value) for value in device_counts.values()))
        new_device = 1.0 if event.device_id and device_seen == 0 else 0.0
        device_rarity = clamp(1.0 - device_seen / total_device_events) if event.device_id else 0.0

        sim_counts = profile["sim_counts"]
        new_sim = 1.0 if event.sim_id and event.sim_id not in sim_counts else 0.0
        ip_counts = profile["ip_prefix_counts"]
        new_ip = 1.0 if event.ip_prefix and event.ip_prefix not in ip_counts else 0.0
        channel_counts = profile["channel_counts"]
        new_channel = 1.0 if history and event.channel.value not in channel_counts else 0.0

        ordered_history = sorted(history, key=lambda item: parse_time(item["occurred_at"]))
        prior_with_channel = [item for item in ordered_history if item.get("channel")]
        transition_novelty = 0.0
        if prior_with_channel:
            previous_channel = str(prior_with_channel[-1].get("channel"))
            pairs = [
                (str(left.get("channel")), str(right.get("channel")))
                for left, right in pairwise(prior_with_channel)
            ]
            pair = (previous_channel, event.channel.value)
            if pairs:
                transition_novelty = clamp(1.0 - pairs.count(pair) / len(pairs))
            elif previous_channel != event.channel.value:
                transition_novelty = 0.75
        recent_cross_channel = [
            item
            for item in prior_with_channel
            if parse_time(item["occurred_at"]) >= occurred_at - timedelta(minutes=15)
            and item.get("channel") != event.channel.value
        ]
        cross_channel_events_15m = clamp(len(recent_cross_channel) / 3.0)
        recent_other_channel_auth = [
            item
            for item in prior_with_channel
            if parse_time(item["occurred_at"]) >= occurred_at - timedelta(hours=24)
            and item.get("channel") != event.channel.value
            and item.get("event_type")
            in {EventType.LOGIN.value, EventType.ACCOUNT_RECOVERY.value, EventType.PIN_RESET.value}
        ]
        new_channel_enrollment_24h = (
            1.0
            if event.event_type in TRANSACTION_TYPES
            and any(
                int(channel_counts.get(str(item.get("channel")), 0)) <= 1
                or (
                    item.get("device_id") is not None
                    and int(device_counts.get(str(item.get("device_id")), 0)) <= 1
                )
                for item in recent_other_channel_auth
            )
            else 0.0
        )
        app_to_ussd_handoff = (
            1.0
            if event.channel == Channel.USSD
            and any(
                item.get("channel") == Channel.APP.value
                and parse_time(item["occurred_at"]) >= occurred_at - timedelta(minutes=30)
                for item in prior_with_channel
            )
            else 0.0
        )
        cross_channel_device_mismatch = 0.0
        if event.device_id and recent_cross_channel:
            prior_devices = {
                item.get("device_id") for item in recent_cross_channel if item.get("device_id")
            }
            if prior_devices and event.device_id not in prior_devices:
                cross_channel_device_mismatch = 1.0

        cutoff_5m = occurred_at - timedelta(minutes=5)
        cutoff_1h = occurred_at - timedelta(hours=1)
        recent_5m = sum(
            1
            for item in history
            if item.get("event_type") in TRANSACTION_TYPES
            and parse_time(item["occurred_at"]) >= cutoff_5m
        )
        recent_1h = sum(
            1
            for item in history
            if item.get("event_type") in TRANSACTION_TYPES
            and parse_time(item["occurred_at"]) >= cutoff_1h
        )
        velocity_5m = clamp(recent_5m / 5.0)
        velocity_1h = clamp(recent_1h / 15.0)

        failed_auth = sum(
            1
            for item in history
            if item.get("event_type") == EventType.FAILED_LOGIN.value
            and parse_time(item["occurred_at"]) >= occurred_at - timedelta(hours=24)
        )
        failed_auth_24h = clamp(failed_auth / 5.0)
        recovery_recent = any(
            item.get("event_type") in {EventType.PIN_RESET.value, EventType.ACCOUNT_RECOVERY.value}
            and parse_time(item["occurred_at"]) >= occurred_at - timedelta(hours=72)
            for item in history
        )
        risk_window = compute_risk_window(history, occurred_at)

        impossible_travel = 0.0
        last_location = profile.get("last_location")
        if last_location and event.latitude is not None and event.longitude is not None:
            previous_time = parse_time(last_location["occurred_at"])
            elapsed_hours = max((occurred_at - previous_time).total_seconds() / 3600.0, 1 / 60)
            distance = haversine_km(
                float(last_location["latitude"]),
                float(last_location["longitude"]),
                event.latitude,
                event.longitude,
            )
            speed = distance / elapsed_hours
            impossible_travel = clamp((speed - 250.0) / 750.0) if speed > 250 else 0.0

        interaction_deviation = 0.0
        if event.interaction_ms and event.menu_depth:
            channel_stats = profile["interaction_stats"].get(event.channel.value)
            if channel_stats and channel_stats["samples"] >= 3:
                current_speed = event.interaction_ms / event.menu_depth
                center = float(channel_stats["median_ms_per_step"])
                scale = max(1.4826 * float(channel_stats["mad_ms_per_step"]), center * 0.1, 50.0)
                interaction_deviation = clamp(abs(current_speed - center) / scale / 6.0)

        typing_deviation = 0.0
        if event.keystroke_interval_ms is not None:
            typing_stats = profile.get("typing_stats", {}).get(event.channel.value)
            if typing_stats and typing_stats["samples"] >= 3:
                center = float(typing_stats["median"])
                scale = max(1.4826 * float(typing_stats["mad"]), center * 0.1, 15.0)
                typing_deviation = clamp(abs(event.keystroke_interval_ms - center) / scale / 6.0)

        paste_anomaly = 0.0
        if event.input_method in {InputMethod.PASTED, InputMethod.MIXED}:
            method_counts = profile.get("input_method_counts", {}).get(event.channel.value, {})
            observed = sum(int(value) for value in method_counts.values())
            historical_paste = int(method_counts.get(InputMethod.PASTED.value, 0)) + int(
                method_counts.get(InputMethod.MIXED.value, 0)
            )
            paste_rate = historical_paste / observed if observed else 0.0
            paste_anomaly = clamp((1.0 - paste_rate) * max(0.25, confidence))

        handling_deviation = 0.0
        if event.device_tilt_variance is not None:
            tilt_stats = profile.get("device_tilt_stats", {}).get(event.channel.value)
            if tilt_stats and tilt_stats["samples"] >= 3:
                center = float(tilt_stats["median"])
                scale = max(1.4826 * float(tilt_stats["mad"]), center * 0.12, 0.05)
                handling_deviation = clamp(abs(event.device_tilt_variance - center) / scale / 6.0)

        navigation_novelty = 0.0
        if event.navigation_signature:
            navigation_counts = profile.get("navigation_counts", {}).get(event.channel.value, {})
            if history and event.navigation_signature not in navigation_counts:
                navigation_novelty = max(0.10, confidence)

        transaction_history = [
            item for item in ordered_history if item.get("event_type") in TRANSACTION_TYPES
        ]
        observed_months = {
            (parse_time(item["occurred_at"]).year, parse_time(item["occurred_at"]).month)
            for item in transaction_history
        }
        calendar_confidence = clamp(len(observed_months) / 4.0)
        day_of_month_deviation = 0.0
        recurring_payment_match = 0.0
        if len(observed_months) >= 3 and transaction_history:
            current_day = occurred_at.day
            historical_days = [parse_time(item["occurred_at"]).day for item in transaction_history]
            nearest_day = min(abs(current_day - day) for day in historical_days)
            day_of_month_deviation = clamp(nearest_day / 12.0)
            if event.recipient_id and event.amount > 0:
                matching = [
                    item
                    for item in transaction_history
                    if item.get("recipient_id") == event.recipient_id
                    and float(item.get("amount", 0.0)) > 0
                    and abs(parse_time(item["occurred_at"]).day - current_day) <= 3
                    and abs(float(item.get("amount", 0.0)) - event.amount) / max(event.amount, 1.0)
                    <= 0.20
                ]
                matching_months = {
                    (parse_time(item["occurred_at"]).year, parse_time(item["occurred_at"]).month)
                    for item in matching
                }
                recurring_payment_match = clamp(len(matching_months) / 3.0)

        coercion = event.coercion_signals
        trusted_coercion = coercion if coercion and coercion.consented_device_attested else None
        call_transfer_overlap = 1.0 if trusted_coercion and trusted_coercion.active_call else 0.0
        screen_sharing_signal = (
            1.0 if trusted_coercion and trusted_coercion.screen_sharing_detected else 0.0
        )
        recipient_edit_anomaly = (
            clamp(trusted_coercion.recipient_replacements / 3.0) if trusted_coercion else 0.0
        )
        confirmation_friction = 0.0
        coercion_on_device_score = 0.0
        coercion_evidence_coverage = 0.0
        if trusted_coercion:
            pause = trusted_coercion.pause_before_confirmation_ms
            hesitation = clamp(((pause or 0) - 30_000) / 120_000.0)
            confirmation_friction = max(
                clamp(trusted_coercion.confirmation_backtracks / 4.0),
                clamp(trusted_coercion.amount_edits / 5.0),
                hesitation,
                1.0 if trusted_coercion.recipient_pasted_during_call else 0.0,
            )
            coercion_on_device_score = trusted_coercion.on_device_coercion_score or 0.0
            values = [
                trusted_coercion.pause_before_confirmation_ms,
                trusted_coercion.on_device_coercion_score,
            ]
            coercion_evidence_coverage = (6 + sum(value is not None for value in values)) / 8.0

        verified_sim_change = 1.0 if event.sim_change_verified and new_sim else 0.0

        assurance = event.telco_assurance
        trusted_assurance = assurance if assurance and assurance.gateway_attested else None
        recent_sim_activation = 0.0
        repeat_sim_change = 0.0
        imsi_change = 0.0
        iccid_change = 0.0
        sim_type_change = 0.0
        otp_sim_change_proximity = 0.0
        otp_sim_geo_mismatch = 0.0
        short_previous_sim_tenure = 0.0
        telco_assurance_coverage = 0.0
        if trusted_assurance:
            values = [
                trusted_assurance.sim_activation_age_hours,
                trusted_assurance.sim_changes_30d,
                trusted_assurance.previous_sim_tenure_days,
                trusted_assurance.otp_to_sim_change_minutes,
                trusted_assurance.otp_sim_geo_distance_km,
            ]
            telco_assurance_coverage = (3 + sum(value is not None for value in values)) / 8.0
            imsi_change = 1.0 if trusted_assurance.imsi_changed else 0.0
            iccid_change = 1.0 if trusted_assurance.iccid_changed else 0.0
            sim_type_change = 1.0 if trusted_assurance.sim_type_changed else 0.0
            if trusted_assurance.sim_activation_age_hours is not None:
                recent_sim_activation = clamp(
                    1.0 - trusted_assurance.sim_activation_age_hours / (24.0 * 7.0)
                )
            if trusted_assurance.sim_changes_30d is not None:
                repeat_sim_change = clamp(trusted_assurance.sim_changes_30d / 3.0)
            if trusted_assurance.otp_to_sim_change_minutes is not None:
                otp_sim_change_proximity = math.exp(
                    -trusted_assurance.otp_to_sim_change_minutes / 360.0
                )
            if trusted_assurance.otp_sim_geo_distance_km is not None:
                otp_sim_geo_mismatch = clamp(trusted_assurance.otp_sim_geo_distance_km / 250.0)
            if trusted_assurance.previous_sim_tenure_days is not None:
                short_previous_sim_tenure = clamp(
                    1.0 - trusted_assurance.previous_sim_tenure_days / 365.0
                )

        if event.channel == Channel.APP:
            evidence_items = [
                event.available_balance_before,
                event.recipient_id,
                event.device_id,
                event.sim_id,
                event.ip_prefix,
                event.latitude,
                event.interaction_ms,
                event.keystroke_interval_ms,
                event.device_tilt_variance,
                event.navigation_signature,
                trusted_assurance,
                trusted_coercion,
            ]
        elif event.channel == Channel.USSD:
            evidence_items = [
                event.available_balance_before,
                event.recipient_id,
                event.sim_id,
                event.ip_prefix,
                event.latitude,
                event.interaction_ms,
                event.navigation_signature,
                trusted_assurance,
                trusted_coercion,
            ]
        elif event.channel == Channel.AGENT:
            evidence_items = [
                event.available_balance_before,
                event.recipient_id,
                event.device_id,
                event.ip_prefix,
                event.latitude,
                event.interaction_ms,
                trusted_assurance,
                trusted_coercion,
                event.agent_assurance
                if event.agent_assurance and event.agent_assurance.gateway_attested
                else None,
            ]
        else:
            evidence_items = [
                event.available_balance_before,
                event.recipient_id,
                event.device_id,
                event.ip_prefix,
                event.latitude,
                event.interaction_ms,
                trusted_assurance,
                trusted_coercion,
            ]
        evidence_coverage = sum(value is not None for value in evidence_items) / len(evidence_items)

        features = {
            "amount_deviation": amount_deviation,
            "amount_to_median": amount_to_median,
            "balance_drain_ratio": balance_drain_ratio,
            "unusual_hour": unusual_hour,
            "new_recipient": new_recipient,
            "recipient_rarity": recipient_rarity,
            "recipient_sender_diversity_24h": recipient_sender_diversity,
            "recipient_first_time_sender_ratio_24h": recipient_first_time_ratio,
            "recipient_inflow_velocity_1h": recipient_inflow_velocity,
            "recipient_rapid_cashout_ratio_1h": recipient_rapid_cashout,
            "recipient_network_coverage": recipient_network_coverage,
            "recipient_confirmed_fraud_score": recipient_confirmed_fraud_score,
            "recipient_confirmed_accounts": recipient_confirmed_accounts,
            "recipient_watchlist_coverage": recipient_watchlist_coverage,
            "new_device": new_device,
            "device_rarity": device_rarity,
            "new_sim": new_sim,
            "new_ip_prefix": new_ip,
            "new_channel": new_channel,
            "channel_transition_novelty": transition_novelty,
            "cross_channel_events_15m": cross_channel_events_15m,
            "new_channel_enrollment_24h": new_channel_enrollment_24h,
            "app_to_ussd_handoff": app_to_ussd_handoff,
            "cross_channel_device_mismatch": cross_channel_device_mismatch,
            "velocity_5m": velocity_5m,
            "velocity_1h": velocity_1h,
            "failed_auth_24h": failed_auth_24h,
            "recovery_signal_72h": 1.0 if recovery_recent else 0.0,
            "account_hazard_score": risk_window["score"],
            "risk_window_hours_remaining": clamp(risk_window["hours_remaining"] / 72.0),
            "impossible_travel": impossible_travel,
            "interaction_speed_deviation": interaction_deviation,
            "typing_cadence_deviation": typing_deviation,
            "paste_anomaly": paste_anomaly,
            "device_handling_deviation": handling_deviation,
            "navigation_novelty": navigation_novelty,
            "day_of_month_deviation": day_of_month_deviation,
            "recurring_payment_match": recurring_payment_match,
            "calendar_confidence": calendar_confidence,
            "call_transfer_overlap": call_transfer_overlap,
            "screen_sharing_signal": screen_sharing_signal,
            "recipient_edit_anomaly": recipient_edit_anomaly,
            "confirmation_friction": confirmation_friction,
            "coercion_on_device_score": coercion_on_device_score,
            "coercion_evidence_coverage": coercion_evidence_coverage,
            "verified_sim_change": verified_sim_change,
            "recent_sim_activation": recent_sim_activation,
            "repeat_sim_change": repeat_sim_change,
            "imsi_change": imsi_change,
            "iccid_change": iccid_change,
            "sim_type_change": sim_type_change,
            "otp_sim_change_proximity": otp_sim_change_proximity,
            "otp_sim_geo_mismatch": otp_sim_geo_mismatch,
            "short_previous_sim_tenure": short_previous_sim_tenure,
            "telco_assurance_coverage": telco_assurance_coverage,
            "evidence_coverage": evidence_coverage,
            "history_confidence": confidence,
            "shared_device_allowed": 1.0 if account.get("shared_device_allowed") else 0.0,
            "is_ussd": 1.0 if event.channel == Channel.USSD else 0.0,
            "is_transfer": 1.0 if event.event_type == EventType.TRANSFER else 0.0,
            "is_withdrawal": 1.0 if event.event_type == EventType.WITHDRAWAL else 0.0,
            "agent_customer_diversity_1h": agent_customer_diversity,
            "is_agent": 1.0 if event.channel == Channel.AGENT else 0.0,
            "agent_recipient_concentration_24h": agent_recipient_concentration,
            "agent_first_time_recipient_ratio_24h": agent_first_time_recipient_ratio,
            "agent_failed_auth_ratio_1h": agent_failed_auth_ratio,
            "agent_value_velocity_1h": agent_value_velocity,
            "agent_location_mismatch": agent_location_mismatch,
            "agent_after_hours": agent_after_hours,
            "agent_terminal_novelty": agent_terminal_novelty,
            "agent_confirmed_fraud_score": agent_confirmed_fraud_score,
            "agent_confirmed_accounts": agent_confirmed_accounts,
            "agent_evidence_coverage": agent_evidence_coverage,
        }
        profile["risk_window"] = risk_window
        return {
            name: round(float(features[name]), 6)
            for name in [*FEATURE_NAMES, *AGENT_FEATURE_NAMES]
        }, profile
