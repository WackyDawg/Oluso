from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aegistwin.config import Settings
from aegistwin.schemas import (
    AccountCreate,
    AgentTerminalAssurance,
    BehaviorEventIn,
    Channel,
    EventType,
    FeedbackLabel,
    FeedbackRequest,
)
from aegistwin.service import AtoService


def assurance(terminal: str, *, attested: bool = True) -> AgentTerminalAssurance:
    return AgentTerminalAssurance(
        agent_token=f"agent_{terminal}",
        terminal_token=terminal,
        registered_latitude=6.5244,
        registered_longitude=3.3792,
        shift_start_hour=6,
        shift_end_hour=22,
        terminal_age_days=540,
        gateway_attested=attested,
    )


def event(
    event_id: str,
    account_id: str,
    at: datetime,
    terminal: str,
    recipient: str | None,
    *,
    event_type: EventType = EventType.TRANSFER,
    attested: bool = True,
) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account_id,
        occurred_at=at,
        event_type=event_type,
        channel=Channel.AGENT,
        amount=2_000 if event_type == EventType.TRANSFER else 0,
        available_balance_before=24_000,
        recipient_id=recipient,
        device_id=f"device_{terminal}",
        ip_prefix="102.88.10.0/24",
        latitude=6.5244,
        longitude=3.3792,
        interaction_ms=24_000,
        menu_depth=6,
        navigation_signature="agent_customer_transfer",
        agent_assurance=assurance(terminal, attested=attested),
        success=event_type != EventType.FAILED_LOGIN,
        metadata={"currency": "NGN", "city": "Lagos", "synthetic_demo": True},
    )


def compact(decision) -> dict[str, object]:
    return {
        "risk_score": decision.score.fused_score,
        "decision_confidence": decision.decision_confidence.score,
        "action": decision.policy.action.value,
        "terminal_status": decision.agent_terminal.status,
        "terminal_quarantined": decision.agent_terminal.quarantined,
        "customer_diversity_1h": decision.feature_snapshot["agent_customer_diversity_1h"],
        "recipient_concentration_24h": decision.feature_snapshot[
            "agent_recipient_concentration_24h"
        ],
        "failed_auth_ratio_1h": decision.feature_snapshot["agent_failed_auth_ratio_1h"],
        "agent_evidence_coverage": decision.feature_snapshot["agent_evidence_coverage"],
        "reasons": [reason.code for reason in decision.reasons],
        "customer_explanation": decision.customer_explanation,
    }


def run(output: Path, database: Path) -> dict[str, object]:
    for suffix in ("", "-wal", "-shm"):
        Path(f"{database}{suffix}").unlink(missing_ok=True)
    settings = Settings(
        environment="demo",
        database_path=database,
        model_path=Path("models/ato_model.joblib"),
        api_key="agent-demo-integration-key",
        analyst_api_key="agent-demo-analyst-key",
        auditor_api_key="agent-demo-auditor-key",
        admin_api_key="agent-demo-admin-key",
    )
    service = AtoService(settings)
    accounts = [f"agent_demo_customer_{index:02d}" for index in range(28)]
    for account_id in accounts:
        service.create_account(AccountCreate(account_id=account_id, display_name=account_id))
    now = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)

    busy_terminal = "terminal_busy_market_demo"
    busy_decision = None
    for index, account_id in enumerate(accounts[:8]):
        busy_decision = service.score_event(
            event(
                f"busy_agent_demo_{index:02d}",
                account_id,
                now + timedelta(minutes=index),
                busy_terminal,
                "registered_market_merchant",
            )
        )
    assert busy_decision is not None

    compromised_terminal = "terminal_compromised_demo"
    for index in range(4):
        service.score_event(
            event(
                f"compromised_agent_failed_{index}",
                accounts[8 + index],
                now + timedelta(minutes=index),
                compromised_terminal,
                None,
                event_type=EventType.FAILED_LOGIN,
            )
        )
    for index in range(5):
        service.score_event(
            event(
                f"compromised_agent_transfer_{index}",
                accounts[12 + index],
                now + timedelta(minutes=4 + index),
                compromised_terminal,
                "mule_agent_hub_demo",
            )
        )
    started = time.perf_counter()
    compromised_decision = service.score_event(
        event(
            "compromised_agent_trigger",
            accounts[17],
            now + timedelta(minutes=9),
            compromised_terminal,
            "mule_agent_hub_demo",
        )
    )
    detection_ms = (time.perf_counter() - started) * 1_000

    feedback_terminal = "terminal_feedback_demo"
    feedback_updates = []
    for index in range(3):
        source = service.score_event(
            event(
                f"agent_feedback_source_{index}",
                accounts[18 + index],
                now + timedelta(minutes=20 + index),
                feedback_terminal,
                f"agent_feedback_recipient_{index}",
            )
        )
        feedback_updates.append(
            service.add_feedback(
                source.decision_id,
                FeedbackRequest(
                    label=FeedbackLabel.ACCOUNT_TAKEOVER,
                    analyst_id=f"analyst_agent_{index}",
                    second_approver_id=(f"independent_agent_{index}" if index else None),
                    notes="synthetic independent customer confirmation",
                ),
            )["agent_terminal_reputation_update"]
        )
    quarantined_decision = service.score_event(
        event(
            "agent_feedback_quarantine_proof",
            accounts[21],
            now + timedelta(minutes=24),
            feedback_terminal,
            "agent_feedback_new_recipient",
        )
    )
    forged_decision = service.score_event(
        event(
            "agent_feedback_forged_claim",
            accounts[22],
            now + timedelta(minutes=25),
            feedback_terminal,
            "agent_feedback_forged_recipient",
            attested=False,
        )
    )

    result = {
        "version": "1.2.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "busy_legitimate_terminal": compact(busy_decision),
        "compromised_terminal": {
            **compact(compromised_decision),
            "detection_ms": round(detection_ms, 3),
        },
        "confirmed_reputation_progression": [
            {
                key: update[key]
                for key in (
                    "status",
                    "score",
                    "confirmed_reports",
                    "distinct_accounts",
                    "quarantined",
                )
            }
            for update in feedback_updates
        ],
        "quarantine_proof": compact(quarantined_decision),
        "forged_unattested_claim": compact(forged_decision),
        "safeguards": {
            "busy_volume_alone_not_campaign": "AGENT_TERMINAL_CAMPAIGN"
            not in compact(busy_decision)["reasons"],
            "compromised_campaign_detected": "AGENT_TERMINAL_CAMPAIGN"
            in compact(compromised_decision)["reasons"],
            "three_victims_required_for_quarantine": feedback_updates[-1][
                "distinct_accounts"
            ]
            == 3,
            "unattested_claim_ignored": forged_decision.feature_snapshot[
                "agent_evidence_coverage"
            ]
            == 0,
        },
        "audit_chain": service.audit.verify(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AegisTwin agent-terminal live proof")
    parser.add_argument("--output", type=Path, default=Path("artifacts/agent_terminal_demo.json"))
    parser.add_argument("--database", type=Path, default=Path("artifacts/agent_terminal_demo.db"))
    args = parser.parse_args()
    result = run(args.output, args.database)
    print(f"busy_action={result['busy_legitimate_terminal']['action']}")
    print(f"compromised_action={result['compromised_terminal']['action']}")
    print(f"quarantined={result['quarantine_proof']['terminal_quarantined']}")
    print(f"audit_valid={result['audit_chain']['valid']}")


if __name__ == "__main__":
    main()
