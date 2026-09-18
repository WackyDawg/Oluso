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
    ConsortiumReportRequest,
    EventType,
    FeedbackLabel,
    FeedbackRequest,
    LifecycleState,
    LifecycleTransitionRequest,
    PolicySimulationRequest,
    TelcoAssurance,
)
from oluso.service import AtoService


def transfer(account: str, event_id: str, at: datetime, recipient: str, *, attack: bool = False) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account,
        occurred_at=at,
        event_type=EventType.TRANSFER,
        channel=Channel.USSD if attack else Channel.APP,
        amount=48_000 if attack else 2_000,
        available_balance_before=52_000 if attack else 40_000,
        recipient_id=recipient,
        device_id="new-device" if attack else "trusted-device",
        sim_id="new-sim" if attack else "trusted-sim",
        interaction_ms=1_100 if attack else 18_000,
        menu_depth=7 if attack else 5,
        telco_assurance=TelcoAssurance(
            imsi_changed=True, iccid_changed=True, sim_activation_age_hours=2,
            gateway_attested=True,
        ) if attack else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/v1_platform_demo.json"))
    args = parser.parse_args()
    db = Path("artifacts/v1_platform_demo.db")
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    service = AtoService(Settings(database_path=db, model_path=Path("models/ato_model.joblib")))
    now = datetime.now(UTC)

    service.create_account(AccountCreate(account_id="safe-learning", display_name="Safe Learning"))
    pending = service.score_event(transfer("safe-learning", "learning-event", now, "merchant"))
    before = service.get_profile("safe-learning").transaction_events
    service.mature_learning(now + timedelta(hours=25))
    matured = service.get_profile("safe-learning").transaction_events
    service.add_feedback(pending.decision_id, FeedbackRequest(
        label=FeedbackLabel.ACCOUNT_TAKEOVER, analyst_id="analyst-one",
        notes="customer callback confirmed compromise",
    ))
    after = service.get_profile("safe-learning").transaction_events

    campaign_decisions = []
    for index in range(4):
        account = f"campaign-{index}"
        service.create_account(AccountCreate(account_id=account, display_name=account))
        service.score_event(transfer(account, f"baseline-{index}", now - timedelta(days=3), "known-shop"))
        campaign_decisions.append(service.score_event(
            transfer(account, f"attack-{index}", now + timedelta(seconds=index), "mule-campaign", attack=True)
        ))

    one = service.consortium_report(ConsortiumReportRequest(
        recipient_id="consortium-mule", institution_id="bank-a", confidence=.90
    ))
    two = service.consortium_report(ConsortiumReportRequest(
        recipient_id="consortium-mule", institution_id="bank-b", confidence=.84
    ))
    service.create_account(AccountCreate(account_id="consortium-victim", display_name="Consortium Victim"))
    consortium_decision = service.score_event(
        transfer("consortium-victim", "consortium-event", now, "consortium-mule")
    )
    replay = service.replay_decision(consortium_decision.decision_id)
    lifecycle = service.transition_lifecycle("consortium-event", LifecycleTransitionRequest(
        target_state=LifecycleState.CANCELLED,
        actor_id="analyst-two",
        reason="independent recipient intelligence confirmed",
        idempotency_key="cancel-consortium-event-001",
    ))

    result = {
        "generated_at": now.isoformat(),
        "safe_learning": {
            "initial_state": pending.learning["trust_state"],
            "profile_transactions_before_maturation": before,
            "after_maturation": matured,
            "after_retroactive_delearning": after,
        },
        "campaign": campaign_decisions[-1].campaign,
        "campaign_action": campaign_decisions[-1].policy.action.value,
        "consortium": {"one_institution": one, "two_institutions": two,
                        "risk": consortium_decision.score.fused_score,
                        "action": consortium_decision.policy.action.value},
        "exact_replay": replay,
        "transaction_lifecycle": lifecycle,
        "governance": {
            "policy_simulation": service.policy_simulation(PolicySimulationRequest()),
            "drift": service.drift_report(),
            "equity": service.equity_report(),
        },
        "audit": service.audit.verify(),
        "telemetry": service.telemetry.snapshot(),
        "metrics": service.database.metrics(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
