from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aegistwin.config import Settings
from aegistwin.fraud_sketch import sign_report, sign_revocation
from aegistwin.schemas import (
    AccountCreate,
    BehaviorEventIn,
    Channel,
    EventType,
    FraudSketchReportRequest,
    FraudSketchRevocationRequest,
)
from aegistwin.service import AtoService, ConflictError


def signed_report(
    settings: Settings,
    *,
    report_id: str,
    institution_id: str,
    indicator_value: str,
    observed_at: datetime,
    nonce: str,
) -> FraudSketchReportRequest:
    payload = {
        "report_id": report_id,
        "institution_id": institution_id,
        "indicator_type": "recipient",
        "indicator_value": indicator_value,
        "confidence": 0.91,
        "evidence_class": "verified_account_takeover",
        "observed_at": observed_at,
        "ttl_hours": 168,
        "nonce": nonce,
    }
    return FraudSketchReportRequest(
        **payload,
        signature=sign_report(
            payload, settings.fraud_sketch_institution_keys[institution_id]
        ),
    )


def seed(service: AtoService, account_id: str, now: datetime) -> None:
    service.create_account(AccountCreate(account_id=account_id, display_name=account_id))
    for index in range(10):
        service.score_event(
            BehaviorEventIn(
                event_id=f"{account_id}_history_{index:02d}",
                account_id=account_id,
                occurred_at=now - timedelta(days=12 - index),
                event_type=EventType.PURCHASE,
                channel=Channel.APP,
                amount=2_200,
                available_balance_before=120_000,
                recipient_id="ordinary-market-merchant",
                device_id="trusted-device",
                sim_id="trusted-sim",
                interaction_ms=9_000,
            )
        )


def event(
    account_id: str,
    event_id: str,
    recipient: str,
    at: datetime,
    *,
    suspicious: bool = False,
) -> BehaviorEventIn:
    return BehaviorEventIn(
        event_id=event_id,
        account_id=account_id,
        occurred_at=at,
        event_type=EventType.TRANSFER,
        channel=Channel.APP,
        amount=48_000 if suspicious else 2_400,
        available_balance_before=100_000,
        recipient_id=recipient,
        device_id="new-remote-device" if suspicious else "trusted-device",
        sim_id="trusted-sim",
        interaction_ms=2_400 if suspicious else 9_000,
    )


def run(project: Path, output: Path) -> dict:
    database = output.with_suffix(".db")
    for path in (database, Path(f"{database}-wal"), Path(f"{database}-shm")):
        if path.exists():
            path.unlink()
    settings = Settings(database_path=database, model_path=project / "models/ato_model.joblib")
    service = AtoService(settings)
    now = datetime.now(UTC)
    indicator = "private-exchange-mule-001"
    for account_id in (
        "exchange-baseline",
        "exchange-observe",
        "exchange-corroborated",
        "exchange-outage",
        "exchange-merchant",
    ):
        seed(service, account_id, now)

    baseline = service.score_event(
        event("exchange-baseline", "exchange_baseline_event", indicator, now)
    )
    first_request = signed_report(
        settings,
        report_id="fsr-001-alpha",
        institution_id="bank-a",
        indicator_value=indicator,
        observed_at=now,
        nonce="fraud-sketch-demo-nonce-alpha",
    )
    started = time.perf_counter()
    first = service.fraud_sketch_report(first_request)
    first_ingest_ms = (time.perf_counter() - started) * 1000

    observe = service.score_event(
        event("exchange-observe", "exchange_observe_event", indicator, now + timedelta(seconds=1))
    )
    second_request = signed_report(
        settings,
        report_id="fsr-002-bravo",
        institution_id="bank-b",
        indicator_value=indicator,
        observed_at=now,
        nonce="fraud-sketch-demo-nonce-bravo",
    )
    started = time.perf_counter()
    second = service.fraud_sketch_report(second_request)
    second_ingest_ms = (time.perf_counter() - started) * 1000

    uncorroborated = service.score_event(
        event(
            "exchange-observe",
            "exchange_shared_watch_event",
            indicator,
            now + timedelta(seconds=2),
        )
    )
    corroborated = service.score_event(
        event(
            "exchange-corroborated",
            "exchange_corroborated_event",
            indicator,
            now + timedelta(seconds=3),
            suspicious=True,
        )
    )

    service.database.set_resilience_state(
        "default",
        "degraded",
        {
            "core_banking": True,
            "telco_gateway": True,
            "consortium": False,
            "recipient_graph": True,
            "agent_integrity": True,
            "model_runtime": True,
        },
        now,
        "online",
        source_id="demo-grid-outage",
    )
    outage = service.score_event(
        event(
            "exchange-outage",
            "exchange_outage_cache_event",
            indicator,
            now + timedelta(seconds=4),
        )
    )

    service.database.set_resilience_state(
        "default",
        "online",
        {
            "core_banking": True,
            "telco_gateway": True,
            "consortium": True,
            "recipient_graph": True,
            "agent_integrity": True,
            "model_runtime": True,
        },
        now + timedelta(seconds=5),
        "degraded",
        source_id="demo-grid-restored",
    )
    merchant = service.score_event(
        event(
            "exchange-merchant",
            "exchange_popular_merchant_event",
            "legitimate-national-biller",
            now + timedelta(seconds=6),
        )
    )

    tampered = first_request.model_copy(update={"confidence": 0.61, "report_id": "fsr-tampered"})
    tamper_rejected = False
    try:
        service.fraud_sketch_report(tampered)
    except ConflictError:
        tamper_rejected = True

    revoke_payload = {
        "report_id": "fsr-002-bravo",
        "institution_id": "bank-b",
        "reason": "synthetic appeal found an incorrect association",
        "revoked_at": datetime.now(UTC),
        "nonce": "fraud-sketch-demo-revoke-bravo",
    }
    revocation = service.revoke_fraud_sketch_report(
        "fsr-002-bravo",
        FraudSketchRevocationRequest(
            **{key: value for key, value in revoke_payload.items() if key != "report_id"},
            signature=sign_revocation(
                revoke_payload, settings.fraud_sketch_institution_keys["bank-b"]
            ),
        ),
    )

    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        shared_rows = [
            dict(row)
            for row in connection.execute(
                "SELECT indicator_type,indicator_token,epoch_id,institution_token,"
                "confidence,evidence_class,status FROM fraud_sketch_reports"
            ).fetchall()
        ]
    shared_serialized = json.dumps(shared_rows, sort_keys=True)
    raw_absent = indicator not in shared_serialized and "bank-a" not in shared_serialized

    result = {
        "version": "1.4.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "actual local service run with synthetic institutions and customers",
        "chronology": "Reports arrive only after the baseline event; every later match uses prior intelligence.",
        "baseline": {
            "risk_score": baseline.score.fused_score,
            "action": baseline.policy.action.value,
        },
        "one_institution": {
            "exchange_score": first["score"],
            "independent_institutions": first["independent_institutions"],
            "other_account_score": observe.score.fused_score,
            "action": observe.policy.action.value,
            "action_ceiling": observe.fraud_sketch_exchange.action_ceiling,
        },
        "two_institutions_without_local_corroboration": {
            "exchange_score": second["score"],
            "risk_score": uncorroborated.score.fused_score,
            "action": uncorroborated.policy.action.value,
            "action_ceiling": uncorroborated.fraud_sketch_exchange.action_ceiling,
        },
        "two_institutions_with_local_corroboration": {
            "risk_score": corroborated.score.fused_score,
            "action": corroborated.policy.action.value,
            "action_ceiling": corroborated.fraud_sketch_exchange.action_ceiling,
            "matched_indicators": corroborated.fraud_sketch_exchange.matched_indicators,
        },
        "outage_cache": {
            "source_mode": outage.fraud_sketch_exchange.source_mode,
            "risk_score": outage.score.fused_score,
            "decision_confidence": outage.decision_confidence.score,
            "capsule_valid": outage.resilience.capsule_valid,
        },
        "legitimate_biller_hard_negative": {
            "exchange_score": merchant.fraud_sketch_exchange.score,
            "risk_score": merchant.score.fused_score,
            "action": merchant.policy.action.value,
        },
        "revocation": revocation,
        "adversarial_controls": {
            "tampered_signature_rejected": tamper_rejected,
            "raw_indicator_absent_from_shared_rows": raw_absent,
            "stored_shared_rows": len(shared_rows),
        },
        "latency_ms": {
            "first_signed_report": round(first_ingest_ms, 3),
            "second_signed_report_and_capsule_refresh": round(second_ingest_ms, 3),
        },
        "audit": service.audit.verify(),
        "privacy_boundary": (
            "Shared tables contain rotating tokens, coarse evidence classes, confidence, expiry and state; "
            "local banking events remain inside the bank database."
        ),
        "production_roadmap": (
            "Replace the prototype consortium token service with VOPRF/PSI or secure aggregation, "
            "HSM-backed keys and formal multi-bank governance."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/fraud_sketch_exchange.json"),
    )
    args = parser.parse_args()
    result = run(args.project.resolve(), args.output.resolve())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
