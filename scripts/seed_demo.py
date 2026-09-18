from __future__ import annotations

import argparse
import uuid
from datetime import UTC, datetime, timedelta

from oluso.config import get_settings
from oluso.schemas import AccountCreate, BehaviorEventIn, Channel, EventType, TelcoAssurance
from oluso.service import AtoService, ConflictError


def event_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a behavioural history and score a takeover scenario")
    parser.add_argument("--account", default="demo_customer_001")
    parser.add_argument("--shared-device", action="store_true")
    args = parser.parse_args()

    service = AtoService(get_settings())
    try:
        service.create_account(
            AccountCreate(
                account_id=args.account,
                display_name="Demo Customer",
                shared_device_allowed=args.shared_device,
                trusted_contact_masked="+234 *** *** 104",
            )
        )
    except ConflictError:
        pass

    now = datetime.now(UTC)
    recipients = ["merchant_grocery", "utility_power", "family_amina"]
    for index in range(36):
        occurred_at = now - timedelta(days=36 - index, hours=index % 3)
        service.score_event(
            BehaviorEventIn(
                event_id=event_id("normal"),
                account_id=args.account,
                occurred_at=occurred_at,
                event_type=EventType.PAYBILL if index % 3 == 0 else EventType.PURCHASE,
                channel=Channel.USSD if index % 2 else Channel.APP,
                amount=1800 + (index % 5) * 220,
                available_balance_before=22_000,
                recipient_id=recipients[index % len(recipients)],
                device_id="device_primary",
                sim_id="sim_primary",
                ip_prefix="102.88.10.0/24",
                latitude=6.5244,
                longitude=3.3792,
                interaction_ms=19_000 + (index % 4) * 900,
                menu_depth=5,
                input_method="typed" if index % 2 == 0 else "unknown",
                keystroke_interval_ms=185 + (index % 4) * 4 if index % 2 == 0 else None,
                device_tilt_variance=2.2 + (index % 3) * 0.1 if index % 2 == 0 else None,
                navigation_signature="app_home_pay" if index % 2 == 0 else "ussd_1_2_1",
            )
        )

    service.score_event(
        BehaviorEventIn(
            event_id=event_id("failed"),
            account_id=args.account,
            occurred_at=now - timedelta(minutes=20),
            event_type=EventType.FAILED_LOGIN,
            channel=Channel.APP,
            device_id="device_unknown",
            sim_id="sim_unknown",
            ip_prefix="197.210.44.0/24",
            success=False,
        )
    )
    decision = service.score_event(
        BehaviorEventIn(
            event_id=event_id("attack"),
            account_id=args.account,
            occurred_at=now,
            event_type=EventType.TRANSFER,
            channel=Channel.USSD,
            amount=48_000,
            available_balance_before=52_000,
            recipient_id="recipient_never_seen",
            device_id="device_unknown",
            sim_id="sim_unknown",
            ip_prefix="197.210.44.0/24",
            latitude=6.5244,
            longitude=3.3792,
            interaction_ms=2_400,
            menu_depth=7,
            navigation_signature="ussd_9_3_1",
            telco_assurance=TelcoAssurance(
                imsi_changed=True,
                iccid_changed=True,
                sim_type_changed=True,
                sim_activation_age_hours=1.5,
                sim_changes_30d=2,
                previous_sim_tenure_days=640,
                otp_to_sim_change_minutes=12,
                otp_sim_geo_distance_km=510,
                gateway_attested=True,
            ),
        )
    )
    print(decision.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
