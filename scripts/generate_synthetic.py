from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from oluso.agent import AgentTerminalTracker
from oluso.features import FeatureEngine
from oluso.network import RecipientNetworkTracker
from oluso.schemas import (
    AgentTerminalAssurance,
    BehaviorEventIn,
    Channel,
    CoercionSignals,
    EventType,
    InputMethod,
    TelcoAssurance,
)

ATTACK_SCENARIOS = [
    "sim_swap_drain",
    "credential_stuffing",
    "recovery_abuse",
    "remote_control_ussd",
    "low_and_slow",
    "agent_social_engineering",
    "coercion_assisted_transfer",
    "cross_channel_takeover",
]

HARD_NEGATIVE_SCENARIOS = [
    "legitimate_travel",
    "legitimate_new_phone",
    "verified_sim_replacement",
    "emergency_transfer",
    "payday_spending",
    "shared_family_phone",
    "popular_merchant_payment",
    "recurring_monthly_payment",
    "busy_agent_merchant_payment",
    "legitimate_post_recovery",
    "legitimate_failed_login_retry",
    "community_collection_payment",
]

NIGERIAN_LOCATIONS = [
    ("Lagos", 6.5244, 3.3792, "102.88.10.0/24"),
    ("Abuja", 9.0765, 7.3986, "105.112.24.0/24"),
    ("Kano", 12.0022, 8.5920, "197.210.8.0/24"),
    ("Port Harcourt", 4.8156, 7.0498, "41.58.32.0/24"),
    ("Ibadan", 7.3775, 3.9470, "102.89.6.0/24"),
    ("Enugu", 6.4584, 7.5464, "197.211.40.0/24"),
]


@dataclass
class Persona:
    account_id: str
    city: str
    latitude: float
    longitude: float
    ip_prefix: str
    primary_channel: str
    typical_amount: float
    typical_hour: int
    primary_device: str
    secondary_device: str
    primary_sim: str
    shared_device_allowed: bool
    regret_limit_30d: int
    interaction_ms_per_step: float
    typing_interval_ms: float
    tilt_variance: float
    recipients: list[str]


def clipped_normal(
    rng: np.random.Generator,
    center: float,
    spread: float,
    lower: float,
    upper: float,
) -> float:
    return float(np.clip(rng.normal(center, spread), lower, upper))


def updated(event: BehaviorEventIn, **changes: Any) -> BehaviorEventIn:
    payload = event.model_dump(mode="json")
    target_channel = str(changes.get("channel", payload.get("channel")))
    if target_channel != Channel.AGENT.value and "agent_assurance" not in changes:
        changes["agent_assurance"] = None
    payload.update(changes)
    return BehaviorEventIn.model_validate(payload)


def profile_payload(event: BehaviorEventIn, *, eligible: bool) -> dict[str, Any]:
    payload = event.model_dump(mode="json")
    payload["_profile_eligible"] = eligible
    return payload


def raw_record(
    event: BehaviorEventIn,
    *,
    scenario: str,
    is_takeover: bool,
    eligible: bool,
) -> dict[str, Any]:
    payload = event.model_dump(mode="json")
    payload["scenario"] = scenario
    payload["is_takeover"] = int(is_takeover)
    payload["profile_eligible"] = int(eligible)
    payload["metadata"] = json.dumps(payload.get("metadata", {}), sort_keys=True)
    payload["telco_assurance"] = json.dumps(
        payload.get("telco_assurance"), sort_keys=True
    ) if payload.get("telco_assurance") is not None else None
    payload["coercion_signals"] = json.dumps(
        payload.get("coercion_signals"), sort_keys=True
    ) if payload.get("coercion_signals") is not None else None
    payload["agent_assurance"] = json.dumps(
        payload.get("agent_assurance"), sort_keys=True
    ) if payload.get("agent_assurance") is not None else None
    return payload


def create_persona(rng: np.random.Generator, index: int) -> Persona:
    city, latitude, longitude, ip_prefix = NIGERIAN_LOCATIONS[index % len(NIGERIAN_LOCATIONS)]
    shared = bool(rng.random() < 0.16)
    primary_channel = str(rng.choice(["ussd", "app", "agent"], p=[0.46, 0.46, 0.08]))
    typical_amount = float(np.exp(rng.normal(np.log(4_500), 0.70)))
    account_id = f"ng_acct_{index + 1:05d}"
    return Persona(
        account_id=account_id,
        city=city,
        latitude=latitude,
        longitude=longitude,
        ip_prefix=ip_prefix,
        primary_channel=primary_channel,
        typical_amount=round(float(np.clip(typical_amount, 500, 75_000)), -1),
        typical_hour=int(rng.integers(6, 22)),
        primary_device=f"device_{index + 1:05d}_primary",
        secondary_device=f"device_{index + 1:05d}_family",
        primary_sim=f"sim_{index + 1:05d}_primary",
        shared_device_allowed=shared,
        regret_limit_30d=int(rng.choice([2, 3, 4], p=[0.15, 0.70, 0.15])),
        interaction_ms_per_step=clipped_normal(rng, 3_600, 650, 1_400, 7_500),
        typing_interval_ms=clipped_normal(rng, 190, 35, 80, 420),
        tilt_variance=clipped_normal(rng, 2.4, 0.55, 0.3, 6.0),
        recipients=[f"ng_recipient_{index + 1:05d}_{suffix}" for suffix in range(5)],
    )


def normal_event(
    rng: np.random.Generator,
    persona: Persona,
    index: int,
    occurred_at: datetime,
) -> BehaviorEventIn:
    if rng.random() < 0.82:
        channel = Channel(persona.primary_channel)
    else:
        alternatives = [Channel.APP, Channel.USSD, Channel.AGENT]
        channel = alternatives[int(rng.integers(0, len(alternatives)))]
    event_type = EventType(
        str(rng.choice(["purchase", "paybill", "transfer"], p=[0.48, 0.32, 0.20]))
    )
    amount = clipped_normal(
        rng,
        persona.typical_amount,
        max(150.0, persona.typical_amount * 0.22),
        100.0,
        persona.typical_amount * 2.1,
    )
    amount = round(amount / 50) * 50
    menu_depth = int(rng.integers(4, 8))
    interaction_ms = int(
        clipped_normal(
            rng,
            persona.interaction_ms_per_step * menu_depth,
            persona.interaction_ms_per_step * 0.15,
            400,
            120_000,
        )
    )
    device_id: str | None = persona.primary_device
    sim_id: str | None = persona.primary_sim
    ip_prefix: str | None = persona.ip_prefix
    latitude: float | None = persona.latitude
    longitude: float | None = persona.longitude
    input_method = InputMethod.UNKNOWN
    typing_interval: float | None = None
    tilt_variance: float | None = None
    agent_assurance = None
    if channel == Channel.APP:
        input_method = InputMethod(
            str(rng.choice(["typed", "mixed", "pasted"], p=[0.94, 0.04, 0.02]))
        )
        typing_interval = clipped_normal(rng, persona.typing_interval_ms, 18, 40, 800)
        tilt_variance = clipped_normal(rng, persona.tilt_variance, 0.28, 0.0, 12.0)
        navigation = str(rng.choice(["app_home_pay", "app_home_bills", "app_quick_pay"]))
    elif channel == Channel.USSD:
        device_id = persona.primary_device if rng.random() < 0.35 else None
        sim_id = persona.primary_sim if rng.random() < 0.92 else None
        ip_prefix = persona.ip_prefix if rng.random() < 0.45 else None
        if rng.random() >= 0.60:
            latitude = None
            longitude = None
        navigation = str(rng.choice(["ussd_1_2_1", "ussd_1_3_1", "ussd_2_1_1"]))
    else:
        terminal_number = int(persona.account_id[-5:]) % 80
        device_id = f"agent_terminal_{terminal_number:03d}"
        sim_id = None
        navigation = "agent_customer_transfer"
        agent_assurance = AgentTerminalAssurance(
            agent_token=f"agent_token_{terminal_number:03d}",
            terminal_token=f"terminal_token_{terminal_number:03d}",
            registered_latitude=persona.latitude,
            registered_longitude=persona.longitude,
            shift_start_hour=6,
            shift_end_hour=22,
            terminal_age_days=clipped_normal(rng, 640, 220, 45, 2_000),
            gateway_attested=True,
        )

    telco_assurance = None
    assurance_probability = 0.62 if channel == Channel.USSD else 0.28
    if rng.random() < assurance_probability:
        telco_assurance = TelcoAssurance(
            sim_activation_age_hours=clipped_normal(rng, 8_000, 2_400, 240, 40_000),
            sim_changes_30d=0,
            previous_sim_tenure_days=clipped_normal(rng, 920, 360, 180, 3_000),
            gateway_attested=True,
        )

    recipient = (
        "national_airtime_merchant"
        if rng.random() < 0.08
        else str(rng.choice(persona.recipients))
    )
    coercion_signals = None
    if channel == Channel.APP and rng.random() < 0.12:
        coercion_signals = CoercionSignals(
            active_call=bool(rng.random() < 0.10),
            recipient_replacements=int(rng.integers(0, 2)),
            confirmation_backtracks=int(rng.integers(0, 2)),
            amount_edits=int(rng.integers(0, 2)),
            pause_before_confirmation_ms=int(rng.integers(4_000, 28_000)),
            on_device_coercion_score=clipped_normal(rng, 0.06, 0.04, 0.0, 0.20),
            consented_device_attested=True,
        )

    return BehaviorEventIn(
        event_id=f"evt_{persona.account_id}_{index:04d}",
        account_id=persona.account_id,
        session_id=f"session_{persona.account_id}_{index:04d}",
        occurred_at=occurred_at,
        event_type=event_type,
        channel=channel,
        amount=amount,
        available_balance_before=max(round(persona.typical_amount * 9, -2), amount * 2.5),
        recipient_id=recipient,
        device_id=device_id,
        sim_id=sim_id,
        ip_prefix=ip_prefix,
        latitude=latitude,
        longitude=longitude,
        interaction_ms=interaction_ms,
        menu_depth=menu_depth,
        input_method=input_method,
        keystroke_interval_ms=typing_interval,
        device_tilt_variance=tilt_variance,
        navigation_signature=navigation,
        telco_assurance=telco_assurance,
        agent_assurance=agent_assurance,
        coercion_signals=coercion_signals,
        metadata={"currency": "NGN", "city": persona.city},
    )


def apply_hard_negative(
    rng: np.random.Generator,
    event: BehaviorEventIn,
    persona: Persona,
    scenario: str,
) -> BehaviorEventIn:
    if scenario == "legitimate_travel":
        city, latitude, longitude, ip_prefix = NIGERIAN_LOCATIONS[
            int(rng.integers(0, len(NIGERIAN_LOCATIONS)))
        ]
        return updated(
            event,
            ip_prefix=ip_prefix,
            latitude=latitude,
            longitude=longitude,
            metadata={"currency": "NGN", "city": city, "travel_context": "domestic"},
        )
    if scenario == "legitimate_new_phone":
        return updated(event, device_id=f"{persona.primary_device}_replacement")
    if scenario == "verified_sim_replacement":
        replacement = f"{persona.primary_sim}_verified"
        persona.primary_sim = replacement
        return updated(
            event,
            sim_id=replacement,
            sim_change_verified=True,
            telco_assurance=TelcoAssurance(
                imsi_changed=True,
                iccid_changed=True,
                sim_type_changed=bool(rng.random() < 0.35),
                sim_activation_age_hours=2.0,
                sim_changes_30d=1,
                previous_sim_tenure_days=720,
                otp_to_sim_change_minutes=15,
                otp_sim_geo_distance_km=2.0,
                gateway_attested=True,
            ),
        )
    if scenario == "emergency_transfer":
        emergency_amount = max(persona.typical_amount * 4.5, 35_000)
        return updated(
            event,
            event_type="transfer",
            amount=round(emergency_amount, -2),
            available_balance_before=round(emergency_amount * 1.35, -2),
            recipient_id=f"hospital_{persona.city.lower().replace(' ', '_')}",
            metadata={"currency": "NGN", "city": persona.city, "customer_context": "emergency"},
        )
    if scenario == "payday_spending":
        return updated(event, amount=round(persona.typical_amount * 3.2, -2))
    if scenario == "popular_merchant_payment":
        return updated(
            event,
            event_type="paybill",
            recipient_id="national_airtime_merchant",
            amount=round(persona.typical_amount * 1.4, -2),
        )
    if scenario == "recurring_monthly_payment":
        return updated(
            event,
            event_type="transfer",
            recipient_id=f"recurring_landlord_{persona.account_id}",
            amount=round(max(12_000, persona.typical_amount * 3.0), -2),
            metadata={"currency": "NGN", "calendar_pattern": "monthly_rent"},
        )
    if scenario == "busy_agent_merchant_payment":
        terminal_number = int(persona.account_id[-5:]) % 12
        return updated(
            event,
            event_type="paybill",
            channel="agent",
            recipient_id="registered_market_merchant",
            amount=round(persona.typical_amount * 1.2, -2),
            device_id=f"busy_agent_terminal_{terminal_number:03d}",
            sim_id=None,
            navigation_signature="agent_registered_merchant_paybill",
            agent_assurance=AgentTerminalAssurance(
                agent_token=f"busy_agent_token_{terminal_number:03d}",
                terminal_token=f"busy_terminal_token_{terminal_number:03d}",
                registered_latitude=event.latitude,
                registered_longitude=event.longitude,
                shift_start_hour=6,
                shift_end_hour=22,
                terminal_age_days=900,
                gateway_attested=True,
            ),
        )
    if scenario == "legitimate_post_recovery":
        return updated(
            event,
            event_type="transfer",
            amount=round(persona.typical_amount * 1.8, -2),
            recipient_id=str(rng.choice(persona.recipients)),
            metadata={"currency": "NGN", "customer_context": "verified_recovery"},
        )
    if scenario == "legitimate_failed_login_retry":
        return updated(
            event,
            event_type="transfer",
            amount=round(persona.typical_amount * 1.4, -2),
            recipient_id=str(rng.choice(persona.recipients)),
            metadata={"currency": "NGN", "customer_context": "successful_retry"},
        )
    if scenario == "community_collection_payment":
        cooperative = int(persona.account_id.rsplit("_", 1)[-1]) % 12
        return updated(
            event,
            event_type="transfer",
            amount=round(max(5_000, persona.typical_amount * 2.2), -2),
            recipient_id=f"community_cooperative_{cooperative:02d}",
            metadata={"currency": "NGN", "customer_context": "community_collection"},
        )
    persona.shared_device_allowed = True
    return updated(event, device_id=persona.secondary_device)


def precursor(
    event: BehaviorEventIn,
    *,
    suffix: str,
    event_type: EventType,
    minutes_before: int,
    success: bool,
) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=f"{event.event_id}_{suffix}",
        account_id=event.account_id,
        session_id=event.session_id,
        occurred_at=event.occurred_at - timedelta(minutes=minutes_before),
        event_type=event_type,
        channel=event.channel,
        amount=0,
        device_id=event.device_id,
        sim_id=event.sim_id,
        ip_prefix=event.ip_prefix,
        success=success,
        metadata={"synthetic_precursor": True},
    )


def monthly_payment_precursors(event: BehaviorEventIn) -> list[BehaviorEventIn]:
    return [
        updated(
            event,
            event_id=f"{event.event_id}_monthly_{days}",
            occurred_at=event.occurred_at - timedelta(days=days),
            amount=round(event.amount * factor, -2),
            metadata={"synthetic_precursor": True, "calendar_pattern": "monthly_rent"},
        )
        for days, factor in ((92, 0.99), (61, 1.01), (31, 1.0))
    ]


def alternate_location(persona: Persona) -> tuple[str, float, float, str]:
    current_index = next(
        index for index, item in enumerate(NIGERIAN_LOCATIONS) if item[0] == persona.city
    )
    return NIGERIAN_LOCATIONS[(current_index + 2) % len(NIGERIAN_LOCATIONS)]


def mule_hub(persona: Persona, family: str = "primary") -> str:
    index = int(persona.account_id.rsplit("_", 1)[-1]) % 8
    return f"mule_hub_{family}_{index:02d}"


def mule_cashout(event: BehaviorEventIn) -> BehaviorEventIn | None:
    if not event.recipient_id or not event.recipient_id.startswith("mule_hub_"):
        return None
    return BehaviorEventIn(
        event_id=f"{event.event_id}_cashout",
        account_id=event.recipient_id,
        session_id=f"cashout_{event.recipient_id}",
        occurred_at=event.occurred_at + timedelta(minutes=10),
        event_type=EventType.WITHDRAWAL,
        channel=Channel.AGENT,
        amount=round(event.amount * 0.88, -2),
        available_balance_before=event.amount,
        recipient_id="cashout_offramp",
        device_id="mule_cashout_terminal",
        ip_prefix="197.210.250.0/24",
        metadata={"synthetic_network_event": True},
    )


def mule_network_precursors(event: BehaviorEventIn) -> list[BehaviorEventIn]:
    """Create prior cross-account fan-in/cash-out evidence without leaking the target label."""

    if not event.recipient_id or not event.recipient_id.startswith("mule_hub_"):
        return []
    feeders = [
        BehaviorEventIn(
            event_id=f"{event.event_id}_feeder_{index}",
            account_id=f"synthetic_feeder_{index}_{event.event_id[-8:]}",
            session_id=f"feeder_session_{event.event_id[-8:]}",
            occurred_at=event.occurred_at - timedelta(minutes=55 - index * 5),
            event_type=EventType.TRANSFER,
            channel=Channel.APP,
            amount=5_000 + index * 500,
            available_balance_before=20_000,
            recipient_id=event.recipient_id,
            device_id=f"feeder_device_{index}",
            success=True,
            metadata={"synthetic_network_event": True},
        )
        for index in range(6)
    ]
    total = sum(item.amount for item in feeders)
    cashout = BehaviorEventIn(
        event_id=f"{event.event_id}_prior_cashout",
        account_id=event.recipient_id,
        session_id=f"mule_session_{event.event_id[-8:]}",
        occurred_at=event.occurred_at - timedelta(minutes=8),
        event_type=EventType.WITHDRAWAL,
        channel=Channel.AGENT,
        amount=round(total * 0.88, -2),
        available_balance_before=total,
        recipient_id="cashout_offramp",
        device_id="mule_cashout_terminal",
        success=True,
        metadata={"synthetic_network_event": True},
    )
    return [*feeders, cashout]


def legitimate_collection_precursors(event: BehaviorEventIn) -> list[BehaviorEventIn]:
    """Create mule-like but legitimate cooperative activity as a hard negative."""

    if not event.recipient_id or not event.recipient_id.startswith("community_cooperative_"):
        return []
    feeders = [
        BehaviorEventIn(
            event_id=f"{event.event_id}_member_{index}",
            account_id=f"cooperative_member_{index}_{event.event_id[-8:]}",
            session_id=f"cooperative_session_{event.event_id[-8:]}",
            occurred_at=event.occurred_at - timedelta(minutes=70 - index * 8),
            event_type=EventType.TRANSFER,
            channel=Channel.USSD,
            amount=2_000 + index * 500,
            available_balance_before=15_000,
            recipient_id=event.recipient_id,
            success=True,
            metadata={"synthetic_network_event": True, "legitimate_cooperative": True},
        )
        for index in range(5)
    ]
    total = sum(item.amount for item in feeders)
    disbursement = BehaviorEventIn(
        event_id=f"{event.event_id}_cooperative_disbursement",
        account_id=event.recipient_id,
        session_id=f"cooperative_disbursement_{event.event_id[-8:]}",
        occurred_at=event.occurred_at - timedelta(minutes=12),
        event_type=EventType.TRANSFER,
        channel=Channel.USSD,
        amount=round(total * 0.28, -2),
        available_balance_before=total,
        recipient_id="verified_cooperative_supplier",
        success=True,
        metadata={"synthetic_network_event": True, "legitimate_cooperative": True},
    )
    return [*feeders, disbursement]


def apply_attack(
    rng: np.random.Generator,
    event: BehaviorEventIn,
    persona: Persona,
    scenario: str,
) -> tuple[BehaviorEventIn, list[BehaviorEventIn]]:
    _, attacker_latitude, attacker_longitude, attacker_ip = alternate_location(persona)
    precursors: list[BehaviorEventIn] = []

    if scenario == "sim_swap_drain":
        attacked = updated(
            event,
            event_type="transfer",
            channel="ussd",
            amount=max(45_000, round(persona.typical_amount * 7, -2)),
            available_balance_before=max(50_000, round(persona.typical_amount * 7.8, -2)),
            recipient_id=mule_hub(persona),
            device_id=f"attacker_device_{persona.account_id}",
            sim_id=f"swapped_sim_{persona.account_id}",
            ip_prefix=attacker_ip,
            latitude=attacker_latitude,
            longitude=attacker_longitude,
            interaction_ms=2_200,
            menu_depth=7,
            input_method="unknown",
            keystroke_interval_ms=None,
            device_tilt_variance=None,
            navigation_signature="ussd_9_3_1",
            sim_change_verified=False,
            telco_assurance=TelcoAssurance(
                imsi_changed=True,
                iccid_changed=True,
                sim_type_changed=bool(rng.random() < 0.55),
                sim_activation_age_hours=clipped_normal(rng, 2.0, 1.0, 0.1, 6.0),
                sim_changes_30d=int(rng.integers(1, 4)),
                previous_sim_tenure_days=clipped_normal(rng, 700, 320, 20, 2_000),
                otp_to_sim_change_minutes=clipped_normal(rng, 22, 14, 1, 90),
                otp_sim_geo_distance_km=clipped_normal(rng, 480, 170, 180, 1_400),
                gateway_attested=True,
            ),
        )
    elif scenario == "credential_stuffing":
        attacked = updated(
            event,
            event_type="transfer",
            channel="app",
            recipient_id=mule_hub(persona),
            device_id=f"attacker_device_{persona.account_id}",
            ip_prefix=attacker_ip,
            input_method="pasted",
            keystroke_interval_ms=42,
            device_tilt_variance=0.04,
            navigation_signature="app_deeplink_transfer",
        )
        precursors = [
            precursor(
                attacked,
                suffix=f"failed_{offset}",
                event_type=EventType.FAILED_LOGIN,
                minutes_before=offset,
                success=False,
            )
            for offset in (32, 24, 16, 8)
        ]
    elif scenario == "recovery_abuse":
        attacked = updated(
            event,
            event_type="transfer",
            amount=max(32_000, round(persona.typical_amount * 5, -2)),
            available_balance_before=max(38_000, round(persona.typical_amount * 6, -2)),
            recipient_id=mule_hub(persona, "recovery"),
            device_id=f"recovery_device_{persona.account_id}",
            sim_id=f"recovery_sim_{persona.account_id}",
        )
        precursors = [
            precursor(
                attacked,
                suffix="recovery",
                event_type=EventType.ACCOUNT_RECOVERY,
                minutes_before=25,
                success=True,
            )
        ]
    elif scenario == "remote_control_ussd":
        attacked = updated(
            event,
            event_type="transfer",
            channel="ussd",
            amount=max(18_000, round(persona.typical_amount * 3.2, -2)),
            recipient_id=mule_hub(persona, "remote"),
            interaction_ms=900,
            menu_depth=8,
            input_method="unknown",
            keystroke_interval_ms=None,
            device_tilt_variance=None,
            navigation_signature="ussd_rapid_4_4_1",
        )
        for offset in (4, 3, 2):
            probe = updated(
                attacked,
                event_id=f"{attacked.event_id}_probe_{offset}",
                occurred_at=attacked.occurred_at - timedelta(minutes=offset),
                amount=500,
                recipient_id=f"probe_mule_{persona.account_id}_{offset}",
            )
            precursors.append(probe)
    elif scenario == "agent_social_engineering":
        attacked = updated(
            event,
            event_type="transfer",
            channel="agent",
            amount=max(30_000, round(persona.typical_amount * 5.5, -2)),
            available_balance_before=max(40_000, round(persona.typical_amount * 6.5, -2)),
            recipient_id=mule_hub(persona, "agent"),
            device_id="agent_terminal_unfamiliar",
            sim_id=None,
            ip_prefix=attacker_ip,
            latitude=attacker_latitude,
            longitude=attacker_longitude,
            navigation_signature="agent_override_transfer",
            agent_assurance=AgentTerminalAssurance(
                agent_token="compromised_agent_token_001",
                terminal_token="compromised_terminal_token_001",
                registered_latitude=persona.latitude,
                registered_longitude=persona.longitude,
                shift_start_hour=6,
                shift_end_hour=22,
                terminal_age_days=480,
                gateway_attested=True,
            ),
        )
    elif scenario == "coercion_assisted_transfer":
        attacked = updated(
            event,
            event_type="transfer",
            channel="app",
            amount=max(24_000, round(persona.typical_amount * 4.2, -2)),
            recipient_id=mule_hub(persona, "coercion"),
            input_method="pasted",
            navigation_signature="app_beneficiary_replaced_confirm",
            coercion_signals=CoercionSignals(
                active_call=True,
                screen_sharing_detected=bool(rng.random() < 0.65),
                recipient_replacements=int(rng.integers(2, 5)),
                confirmation_backtracks=int(rng.integers(2, 6)),
                amount_edits=int(rng.integers(1, 5)),
                pause_before_confirmation_ms=int(rng.integers(75_000, 240_000)),
                recipient_pasted_during_call=True,
                on_device_coercion_score=clipped_normal(rng, 0.82, 0.10, 0.55, 0.99),
                consented_device_attested=True,
            ),
        )
    elif scenario == "cross_channel_takeover":
        attacked = updated(
            event,
            event_type="transfer",
            channel="ussd",
            amount=max(22_000, round(persona.typical_amount * 4.0, -2)),
            recipient_id=mule_hub(persona, "cross_channel"),
            device_id=persona.primary_device,
            sim_id=persona.primary_sim,
            navigation_signature="ussd_1_4_2",
        )
        precursors = [
            BehaviorEventIn(
                event_id=f"{attacked.event_id}_new_app_login",
                account_id=attacked.account_id,
                session_id=f"cross_channel_{attacked.account_id}",
                occurred_at=attacked.occurred_at - timedelta(minutes=8),
                event_type=EventType.LOGIN,
                channel=Channel.APP,
                amount=0,
                device_id=f"enrolment_device_{persona.account_id}",
                sim_id=persona.primary_sim,
                ip_prefix=attacker_ip,
                success=True,
                metadata={"synthetic_precursor": True, "new_channel_enrolment": True},
            )
        ]
    else:
        attacked = updated(
            event,
            event_type="transfer",
            amount=round(persona.typical_amount * float(rng.uniform(1.05, 1.55)), -2),
            recipient_id=mule_hub(persona, "slow"),
            ip_prefix=attacker_ip if rng.random() < 0.20 else event.ip_prefix,
            input_method=event.input_method,
            navigation_signature=event.navigation_signature,
        )
    return attacked, precursors


def generate(
    rows: int,
    seed: int,
    fraud_rate: float,
    hard_negative_rate: float,
    accounts: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    account_count = accounts or max(250, rows // 40)
    personas = [create_persona(rng, index) for index in range(account_count)]
    feature_engine = FeatureEngine()
    histories: dict[str, list[dict[str, Any]]] = {persona.account_id: [] for persona in personas}
    raw_records: list[dict[str, Any]] = []
    network = RecipientNetworkTracker()
    agent_network = AgentTerminalTracker()
    feature_records: list[dict[str, Any]] = []
    recipient_reports: dict[str, set[str]] = {}
    pending_reports: list[tuple[datetime, str, str]] = []
    start = datetime(2025, 1, 1, tzinfo=UTC)

    for row_index in range(rows):
        persona = personas[row_index % account_count]
        local_index = row_index // account_count
        occurred_at = (
            start
            + timedelta(days=local_index * 4, minutes=(row_index % account_count) * 3)
            + timedelta(hours=persona.typical_hour)
            + timedelta(minutes=int(rng.integers(-90, 91)))
        )
        event = normal_event(rng, persona, local_index, occurred_at)
        matured_reports = [item for item in pending_reports if item[0] <= occurred_at]
        pending_reports = [item for item in pending_reports if item[0] > occurred_at]
        for _, recipient_id, reporting_account in matured_reports:
            recipient_reports.setdefault(recipient_id, set()).add(reporting_account)
        mature_enough = local_index >= 8
        is_takeover = mature_enough and bool(rng.random() < fraud_rate)
        is_hard_negative = (
            mature_enough and not is_takeover and bool(rng.random() < hard_negative_rate)
        )

        if is_takeover:
            scenario = str(rng.choice(ATTACK_SCENARIOS))
            event, precursors = apply_attack(rng, event, persona, scenario)
            reuse_probability = {
                "sim_swap_drain": 0.20,
                "credential_stuffing": 0.35,
                "recovery_abuse": 0.30,
                "remote_control_ussd": 0.25,
                "low_and_slow": 0.80,
                "agent_social_engineering": 0.25,
                "coercion_assisted_transfer": 0.45,
                "cross_channel_takeover": 0.45,
            }[scenario]
            seen_recipients = sorted(
                {
                    str(item["recipient_id"])
                    for item in histories[persona.account_id]
                    if item.get("recipient_id")
                }
            )
            if seen_recipients and rng.random() < reuse_probability:
                metadata = dict(event.metadata)
                metadata["synthetic_groomed_recipient"] = True
                event = updated(
                    event,
                    recipient_id=str(rng.choice(seen_recipients)),
                    metadata=metadata,
                )
            for prior in sorted(precursors, key=lambda item: item.occurred_at):
                histories[persona.account_id].append(profile_payload(prior, eligible=False))
                network.add(profile_payload(prior, eligible=False))
                agent_network.add(profile_payload(prior, eligible=False))
                raw_records.append(
                    raw_record(prior, scenario=scenario, is_takeover=True, eligible=False)
                )
            if scenario != "low_and_slow" and rng.random() < 0.30:
                for network_event in mule_network_precursors(event):
                    network.add(profile_payload(network_event, eligible=False))
                    agent_network.add(profile_payload(network_event, eligible=False))
                    raw_records.append(
                        raw_record(
                            network_event,
                            scenario="mule_network_precursor",
                            is_takeover=True,
                            eligible=False,
                        )
                    )
        elif is_hard_negative:
            scenario = str(rng.choice(HARD_NEGATIVE_SCENARIOS))
            event = apply_hard_negative(rng, event, persona, scenario)
            if scenario == "recurring_monthly_payment":
                for prior in monthly_payment_precursors(event):
                    histories[persona.account_id].append(profile_payload(prior, eligible=True))
                    network.add(profile_payload(prior, eligible=True))
                    agent_network.add(profile_payload(prior, eligible=True))
                    raw_records.append(
                        raw_record(prior, scenario=scenario, is_takeover=False, eligible=True)
                    )
            elif scenario in {"legitimate_post_recovery", "legitimate_failed_login_retry"}:
                event_type = (
                    EventType.ACCOUNT_RECOVERY
                    if scenario == "legitimate_post_recovery"
                    else EventType.FAILED_LOGIN
                )
                offsets = (35,) if scenario == "legitimate_post_recovery" else (28, 16, 7)
                for offset in offsets:
                    prior = precursor(
                        event,
                        suffix=f"legitimate_{offset}",
                        event_type=event_type,
                        minutes_before=offset,
                        success=event_type == EventType.ACCOUNT_RECOVERY,
                    )
                    histories[persona.account_id].append(profile_payload(prior, eligible=False))
                    network.add(profile_payload(prior, eligible=False))
                    agent_network.add(profile_payload(prior, eligible=False))
                    raw_records.append(
                        raw_record(prior, scenario=scenario, is_takeover=False, eligible=False)
                    )
            elif scenario == "community_collection_payment":
                for prior in legitimate_collection_precursors(event):
                    network.add(profile_payload(prior, eligible=True))
                    agent_network.add(profile_payload(prior, eligible=True))
                    raw_records.append(
                        raw_record(prior, scenario=scenario, is_takeover=False, eligible=True)
                    )
        else:
            scenario = "legitimate"

        account = {
            "account_id": persona.account_id,
            "shared_device_allowed": persona.shared_device_allowed,
        }
        recipient_context = network.summarize(
            event.recipient_id,
            event.account_id,
            event.occurred_at,
        )
        confirmed_accounts = len(recipient_reports.get(event.recipient_id or "", set()))
        recipient_context.update(
            {
                "confirmed_fraud_score": (
                    0.0
                    if confirmed_accounts == 0
                    else 0.35
                    if confirmed_accounts == 1
                    else 0.75
                    if confirmed_accounts == 2
                    else 1.0
                ),
                "confirmed_distinct_accounts": confirmed_accounts,
                "watchlist_evidence_available": 1.0 if event.recipient_id else 0.0,
            }
        )
        agent_context = agent_network.summarize(event)
        features, _ = feature_engine.extract(
            event,
            histories[persona.account_id],
            account,
            recipient_context,
            agent_context,
        )
        feature_records.append(
            {
                "event_time": event.occurred_at.isoformat(),
                "event_id": event.event_id,
                "session_id": event.session_id,
                "account_id": event.account_id,
                "channel": event.channel.value,
                "scenario": scenario,
                **features,
                "is_takeover": int(is_takeover),
            }
        )
        eligible = not is_takeover
        histories[persona.account_id].append(profile_payload(event, eligible=eligible))
        network.add(profile_payload(event, eligible=eligible))
        agent_network.add(profile_payload(event, eligible=eligible))
        raw_records.append(
            raw_record(event, scenario=scenario, is_takeover=is_takeover, eligible=eligible)
        )
        if is_takeover:
            if (
                event.recipient_id
                and event.recipient_id.startswith("mule_hub_")
                and rng.random() < 0.70
            ):
                pending_reports.append(
                    (
                        event.occurred_at + timedelta(days=int(rng.integers(2, 15))),
                        event.recipient_id,
                        event.account_id,
                    )
                )
            cashout = mule_cashout(event)
            if cashout:
                network.add(profile_payload(cashout, eligible=False))
                raw_records.append(
                    raw_record(cashout, scenario="mule_cashout", is_takeover=True, eligible=False)
                )

    features_frame = pd.DataFrame.from_records(feature_records).sort_values("event_time")
    events_frame = pd.DataFrame.from_records(raw_records).sort_values("occurred_at")
    accounts_frame = pd.DataFrame.from_records([asdict(persona) for persona in personas])
    return (
        features_frame.reset_index(drop=True),
        events_frame.reset_index(drop=True),
        accounts_frame.reset_index(drop=True),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate raw longitudinal Nigerian banking sessions and derived ATO features"
    )
    parser.add_argument("--rows", type=int, default=30_000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--fraud-rate", type=float, default=0.01)
    parser.add_argument("--hard-negative-rate", type=float, default=0.12)
    parser.add_argument("--accounts", type=int)
    parser.add_argument("--output", type=Path, default=Path("data/training_features.csv"))
    parser.add_argument("--events-output", type=Path, default=Path("data/synthetic_events.csv"))
    parser.add_argument("--accounts-output", type=Path, default=Path("data/synthetic_accounts.csv"))
    args = parser.parse_args()
    if not 0 < args.fraud_rate < 0.20:
        raise ValueError("fraud-rate must be between 0 and 0.20")
    if not 0 <= args.hard_negative_rate < 0.80:
        raise ValueError("hard-negative-rate must be between 0 and 0.80")

    features, events, accounts = generate(
        args.rows,
        args.seed,
        args.fraud_rate,
        args.hard_negative_rate,
        args.accounts,
    )
    for path in (args.output, args.events_output, args.accounts_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(args.output, index=False)
    events.to_csv(args.events_output, index=False)
    accounts.to_csv(args.accounts_output, index=False)
    print(
        f"features={args.output} rows={len(features)} takeover_rate="
        f"{features['is_takeover'].mean():.4f}"
    )
    print(f"raw_events={args.events_output} rows={len(events)}")
    print(f"accounts={args.accounts_output} rows={len(accounts)}")
    print(features.groupby(["is_takeover", "scenario"]).size().to_string())


if __name__ == "__main__":
    main()
