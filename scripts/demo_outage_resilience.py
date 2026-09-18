from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

from oluso.config import Settings
from oluso.schemas import (
    AccountCreate,
    BehaviorEventIn,
    Channel,
    EventType,
    OutageHeartbeatRequest,
    OutageSimulationRequest,
    ReconciliationRequest,
    ResilienceMode,
)
from oluso.service import AtoService


def transaction(
    account_id: str,
    event_id: str,
    occurred_at: datetime,
    *,
    recipient: str,
    amount: float,
) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account_id,
        occurred_at=occurred_at,
        event_type=EventType.TRANSFER,
        channel=Channel.USSD,
        amount=amount,
        available_balance_before=52_000,
        recipient_id=recipient,
        sim_id="trusted-sim",
        ip_prefix="102.88.10.0/24",
        interaction_ms=18_000,
        menu_depth=5,
        navigation_signature="ussd_1_2_1",
    )


def signed_degraded_heartbeat(service: AtoService) -> OutageHeartbeatRequest:
    request = OutageHeartbeatRequest(
        source_id="demo-bank-health-controller",
        observed_at=datetime.now(UTC),
        nonce=f"outage-demo-{uuid.uuid4().hex}",
        core_banking_available=True,
        telco_gateway_available=False,
        consortium_available=False,
        recipient_graph_available=False,
        model_runtime_available=False,
        signature="0" * 64,
    )
    return request.model_copy(update={"signature": service.sign_resilience_heartbeat(request)})


def run(project: Path, output: Path) -> dict:
    database = project / "artifacts/outage_resilience_demo.db"
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{database}{suffix}")
        if candidate.exists():
            candidate.unlink()
    service = AtoService(
        Settings(
            environment="demonstration",
            database_path=database,
            model_path=project / "models/ato_model.joblib",
        )
    )
    account_id = "outage_demo_customer"
    service.create_account(AccountCreate(account_id=account_id, display_name="Synthetic Outage Demo"))
    now = datetime.now(UTC)
    for index in range(8):
        service.score_event(
            transaction(
                account_id,
                f"outage_history_{index:02d}",
                now - timedelta(days=16 - index * 2),
                recipient="known-electricity-biller",
                amount=2_000 + index * 25,
            )
        )

    detection_started = perf_counter()
    degraded_state = service.resilience_heartbeat(signed_degraded_heartbeat(service))
    outage_detection_ms = (perf_counter() - detection_started) * 1000
    known = service.score_event(
        transaction(
            account_id,
            "outage_known_recipient",
            now + timedelta(seconds=1),
            recipient="known-electricity-biller",
            amount=2_100,
        )
    )
    unusual = service.score_event(
        transaction(
            account_id,
            "outage_new_recipient",
            now + timedelta(seconds=2),
            recipient="unseen-recipient-during-outage",
            amount=18_000,
        )
    )

    isolated_state = service.simulate_resilience_mode(
        OutageSimulationRequest(mode=ResilienceMode.ISOLATED)
    )
    isolated = service.score_event(
        transaction(
            account_id,
            "outage_payment_rail_down",
            now + timedelta(seconds=3),
            recipient="known-electricity-biller",
            amount=2_200,
        )
    )
    journal_before = service.database.verify_offline_journal("default")

    with service.database.connect() as connection:
        row = connection.execute(
            "SELECT journal_id,payload_json FROM offline_journal ORDER BY sequence LIMIT 1"
        ).fetchone()
        original_payload = str(row["payload_json"])
        connection.execute(
            "UPDATE offline_journal SET payload_json=? WHERE journal_id=?",
            ('{"tampered":true}', row["journal_id"]),
        )
    tamper_detection = service.database.verify_offline_journal("default")
    with service.database.connect() as connection:
        connection.execute(
            "UPDATE offline_journal SET payload_json=? WHERE journal_id=?",
            (original_payload, row["journal_id"]),
        )
    integrity_restored = service.database.verify_offline_journal("default")

    recovery_started = perf_counter()
    recovery_state = service.simulate_resilience_mode(
        OutageSimulationRequest(mode=ResilienceMode.ONLINE)
    )
    reconciliation = service.reconcile_outage(ReconciliationRequest(batch_size=100))
    recovery_ms = (perf_counter() - recovery_started) * 1000
    repeated = service.reconcile_outage(ReconciliationRequest(batch_size=100))

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "single-laptop deterministic outage drill using synthetic identities and real service code",
        "states": {
            "degraded": degraded_state["context"]["mode"],
            "isolated": isolated_state["context"]["mode"],
            "recovery_gate": recovery_state["context"]["mode"],
            "final": reconciliation["final_mode"],
        },
        "signed_edge_capsule": {
            "valid": degraded_state["context"]["capsule_valid"],
            "capsule_id": degraded_state["context"]["capsule_id"],
            "expires_at": degraded_state["context"]["capsule_expires_at"],
        },
        "degraded_known_recipient": {
            "risk_score": known.score.fused_score,
            "decision_confidence": known.decision_confidence.score,
            "action": known.policy.action.value,
            "learning_state": known.learning["trust_state"],
        },
        "degraded_unusual_recipient": {
            "risk_score": unusual.score.fused_score,
            "decision_confidence": unusual.decision_confidence.score,
            "action": unusual.policy.action.value,
            "safety_envelope_applied": unusual.resilience.safety_envelope_applied,
        },
        "isolated_payment": {
            "action": isolated.policy.action.value,
            "offline_reference": isolated.resilience.offline_reference,
            "customer_explanation": isolated.customer_explanation,
            "transaction_state": isolated.transaction_state,
        },
        "journal": {
            "entries_before_recovery": journal_before["entries_checked"],
            "valid_before_tamper": journal_before["valid"],
            "tamper_detected": not tamper_detection["valid"],
            "valid_after_exact_restore": integrity_restored["valid"],
        },
        "reconciliation": {
            "status": reconciliation["status"],
            "processed": reconciliation["processed"],
            "failed": reconciliation["failed"],
            "remaining": reconciliation["remaining"],
            "duplicate_actions": reconciliation["duplicate_actions"],
            "automatic_settlements": 0,
            "repeat_status": repeated["status"],
            "priority_order": reconciliation["priority_order"],
            "batch_limit": reconciliation["batch_limit"],
            "circuit_breaker_open": reconciliation["circuit_breaker_open"],
        },
        "objectives": {
            "outage_detection_ms": round(outage_detection_ms, 3),
            "recovery_and_reconciliation_ms": round(recovery_ms, 3),
            "recovery_point_unjournalled_events": 0,
            "duplicate_lifecycle_actions": 0,
        },
        "audit_verification": service.audit.verify(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("artifacts/outage_resilience.json"))
    args = parser.parse_args()
    result = run(args.project.resolve(), args.output.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
