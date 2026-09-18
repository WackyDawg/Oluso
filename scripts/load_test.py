from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path

from oluso.config import Settings
from oluso.schemas import AccountCreate, BehaviorEventIn, Channel, EventType
from oluso.service import AtoService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("artifacts/concurrent_load.json"))
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("artifacts/load_test.db"),
        help="Scratch SQLite path; keep it off synced folders (OneDrive/Dropbox) for honest timings.",
    )
    args = parser.parse_args()
    database = args.database
    for runtime_file in (
        database,
        Path(f"{database}-wal"),
        Path(f"{database}-shm"),
    ):
        runtime_file.unlink(missing_ok=True)
    service = AtoService(Settings(database_path=database, model_path=Path("models/ato_model.joblib")))
    now = datetime.now(UTC)
    accounts = [f"load-{index}" for index in range(args.workers)]
    for account in accounts:
        service.create_account(AccountCreate(account_id=account, display_name=account))

    def score(index: int) -> float:
        account = accounts[index % len(accounts)]
        event = BehaviorEventIn(
            event_id=f"load-event-{index:06d}", account_id=account,
            occurred_at=now + timedelta(milliseconds=index), event_type=EventType.PURCHASE,
            channel=Channel.APP, amount=1_000 + index % 50,
            recipient_id="load-merchant", device_id=f"device-{account}", sim_id=f"sim-{account}",
        )
        started = time.perf_counter()
        service.score_event(event)
        return (time.perf_counter() - started) * 1000

    # Measure steady-state service behavior after model and SQLite paths are loaded.
    for index, account in enumerate(accounts):
        service.score_event(
            BehaviorEventIn(
                event_id=f"load-warmup-{index:03d}",
                account_id=account,
                occurred_at=now - timedelta(seconds=args.workers - index),
                event_type=EventType.PURCHASE,
                channel=Channel.APP,
                amount=950,
                recipient_id="load-merchant",
                device_id=f"device-{account}",
                sim_id=f"sim-{account}",
            )
        )

    started = time.perf_counter()
    latencies: list[float] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(score, index) for index in range(args.requests)]
        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except (RuntimeError, ValueError, sqlite3.Error) as exc:
                failures.append(type(exc).__name__)
    elapsed = time.perf_counter() - started
    ordered = sorted(latencies)
    percentile = (
        lambda p: ordered[
            max(0, min(len(ordered) - 1, math.ceil(len(ordered) * p) - 1))
        ]
        if ordered
        else 0.0
    )
    report = {
        "requests": args.requests, "workers": args.workers,
        "warmup_requests": len(accounts),
        "successes": len(latencies), "failures": len(failures), "failure_types": failures,
        "throughput_requests_per_second": round(len(latencies) / elapsed, 3),
        "latency_ms": {"mean": round(statistics.mean(latencies), 3) if latencies else 0.0,
                       "p50": round(percentile(.50), 3), "p95": round(percentile(.95), 3),
                       "p99": round(percentile(.99), 3), "max": round(max(latencies), 3) if latencies else 0.0},
        "audit_valid": service.audit.verify()["valid"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
