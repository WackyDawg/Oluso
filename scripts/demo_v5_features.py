from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from oluso.config import Settings
from oluso.schemas import (
    AccountCreate,
    BehaviorEventIn,
    Channel,
    EventType,
    FeedbackLabel,
    FeedbackRequest,
)
from oluso.service import AtoService


def seed(service: AtoService, account_id: str, now: datetime, channel: Channel) -> None:
    service.create_account(AccountCreate(account_id=account_id, display_name=account_id))
    for index in range(24):
        service.score_event(
            BehaviorEventIn(
                event_id=f"{account_id}_baseline_{index:02d}",
                account_id=account_id,
                occurred_at=now - timedelta(days=(24 - index) * 5),
                event_type=EventType.PURCHASE,
                channel=channel,
                amount=7_500 + (index % 3) * 250,
                available_balance_before=80_000,
                recipient_id="merchant_known",
                device_id="device_known",
                sim_id="sim_known",
                ip_prefix="102.88.10.0/24",
                interaction_ms=20_000,
                menu_depth=5,
                navigation_signature=("ussd_1_2_1" if channel == Channel.USSD else "app_home_pay"),
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the five Oluso v0.5 live proof cases")
    parser.add_argument("--database", type=Path, default=Path("artifacts/v5_demo.db"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/v5_feature_demo.json"))
    args = parser.parse_args()
    for suffix in ("", "-wal", "-shm"):
        Path(f"{args.database}{suffix}").unlink(missing_ok=True)
    settings = Settings(
        environment="demo",
        database_path=args.database,
        model_path=Path("models/ato_model.joblib"),
        api_key="demo-v5-api-key",
        profile_lookback_days=180,
        max_history_events=2_000,
    )
    service = AtoService(settings)
    now = datetime.now(UTC).replace(microsecond=0)

    service.create_account(AccountCreate(account_id="confidence_cold", display_name="Cold"))
    cold = service.score_event(
        BehaviorEventIn(
            event_id="confidence_cold_event",
            account_id="confidence_cold",
            occurred_at=now,
            event_type=EventType.TRANSFER,
            channel=Channel.USSD,
            amount=500,
            recipient_id="local_shop",
        )
    )

    seed(service, "cross_channel", now, Channel.USSD)
    service.score_event(
        BehaviorEventIn(
            event_id="cross_channel_app_enrolment",
            account_id="cross_channel",
            occurred_at=now + timedelta(seconds=1),
            event_type=EventType.LOGIN,
            channel=Channel.APP,
            device_id="attacker_enrolment_device",
            sim_id="sim_known",
            ip_prefix="197.210.44.0/24",
        )
    )
    cross = service.score_event(
        BehaviorEventIn(
            event_id="cross_channel_ussd_transfer",
            account_id="cross_channel",
            occurred_at=now + timedelta(minutes=8),
            event_type=EventType.TRANSFER,
            channel=Channel.USSD,
            amount=22_000,
            available_balance_before=80_000,
            recipient_id="recipient_cross_channel",
            device_id="device_known",
            sim_id="sim_known",
            interaction_ms=14_000,
            menu_depth=5,
            navigation_signature="ussd_1_4_2",
        )
    )

    seed(service, "watchlist_a", now, Channel.APP)
    seed(service, "watchlist_b", now, Channel.APP)
    source = service.score_event(
        BehaviorEventIn(
            event_id="watchlist_source",
            account_id="watchlist_a",
            occurred_at=now + timedelta(minutes=20),
            event_type=EventType.TRANSFER,
            channel=Channel.APP,
            amount=8_000,
            available_balance_before=80_000,
            recipient_id="recipient_confirmed_bad",
            device_id="device_known",
            sim_id="sim_known",
            interaction_ms=20_000,
            menu_depth=5,
            navigation_signature="app_home_pay",
        )
    )
    feedback = service.add_feedback(
        source.decision_id,
        FeedbackRequest(
            label=FeedbackLabel.ACCOUNT_TAKEOVER,
            analyst_id="demo_analyst",
            notes="Customer confirmed the transfer was unauthorised.",
        ),
    )
    propagated = service.score_event(
        BehaviorEventIn(
            event_id="watchlist_propagated",
            account_id="watchlist_b",
            occurred_at=now + timedelta(minutes=21),
            event_type=EventType.TRANSFER,
            channel=Channel.APP,
            amount=8_000,
            available_balance_before=80_000,
            recipient_id="recipient_confirmed_bad",
            device_id="device_known",
            sim_id="sim_known",
            interaction_ms=20_000,
            menu_depth=5,
            navigation_signature="app_home_pay",
        )
    )

    seed(service, "calendar_twin", now, Channel.APP)
    for index, days in enumerate((92, 61, 31)):
        service.score_event(
            BehaviorEventIn(
                event_id=f"calendar_prior_{index}",
                account_id="calendar_twin",
                occurred_at=now - timedelta(days=days),
                event_type=EventType.TRANSFER,
                channel=Channel.APP,
                amount=20_000,
                available_balance_before=80_000,
                recipient_id="landlord_monthly",
                device_id="device_known",
                sim_id="sim_known",
                interaction_ms=20_000,
                menu_depth=5,
                navigation_signature="app_home_pay",
            )
        )
    calendar = service.score_event(
        BehaviorEventIn(
            event_id="calendar_current",
            account_id="calendar_twin",
            occurred_at=now + timedelta(minutes=30),
            event_type=EventType.TRANSFER,
            channel=Channel.APP,
            amount=20_000,
            available_balance_before=80_000,
            recipient_id="landlord_monthly",
            device_id="device_known",
            sim_id="sim_known",
            interaction_ms=20_000,
            menu_depth=5,
            navigation_signature="app_home_pay",
        )
    )

    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_version": service.model_bundle.version,
        "confidence_envelope": {
            "risk_score": cold.score.fused_score,
            "decision_confidence": cold.decision_confidence.model_dump(mode="json"),
            "action": cold.policy.action.value,
        },
        "cross_channel_sequence": {
            "risk_score": cross.score.fused_score,
            "action": cross.policy.action.value,
            "reason_codes": [item.code for item in cross.reasons],
            "features": {
                key: cross.feature_snapshot[key]
                for key in (
                    "channel_transition_novelty",
                    "new_channel_enrollment_24h",
                    "app_to_ussd_handoff",
                )
            },
        },
        "recipient_reputation_loop": {
            "source_score": source.score.fused_score,
            "feedback_update": feedback["recipient_reputation_update"],
            "other_account_score": propagated.score.fused_score,
            "other_account_action": propagated.policy.action.value,
            "reason_codes": [item.code for item in propagated.reasons],
        },
        "calendar_twin": {
            "risk_score": calendar.score.fused_score,
            "action": calendar.policy.action.value,
            "recurring_payment_match": calendar.feature_snapshot["recurring_payment_match"],
            "calendar_confidence": calendar.feature_snapshot["calendar_confidence"],
        },
        "friction_optimizer": {
            "selected_action": cross.policy.action.value,
            "selected_expected_cost": cross.policy.selected_expected_cost,
            "action_costs": cross.policy.action_costs,
            "personalization_reasons": cross.policy.personalization_reasons,
        },
        "audit_chain_valid": service.audit.verify()["valid"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
