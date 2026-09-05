from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
from fastapi.testclient import TestClient

from aegistwin.api import create_app
from aegistwin.config import Settings


def event_payload(index: int, occurred_at: datetime, prefix: str) -> dict[str, object]:
    return {
        "event_id": f"{prefix}_{index:05d}",
        "account_id": "ng_latency_account",
        "occurred_at": occurred_at.isoformat(),
        "event_type": "purchase",
        "channel": "ussd",
        "amount": 2_200 + (index % 4) * 50,
        "available_balance_before": 50_000,
        "recipient_id": "lagos_grocery",
        "sim_id": "known_sim",
        "interaction_ms": 12_100 + (index % 3) * 80,
        "menu_depth": 5,
        "navigation_signature": "ussd_1_2_1",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark warm end-to-end API scoring latency")
    parser.add_argument("--requests", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=30)
    parser.add_argument("--model", type=Path, default=Path("models/ato_model.joblib"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/latency.json"))
    args = parser.parse_args()

    with TemporaryDirectory(prefix="aegistwin-latency-") as temporary_directory:
        settings = Settings(
            environment="benchmark",
            database_path=Path(temporary_directory) / "benchmark.db",
            model_path=args.model,
            api_key="benchmark-api-key-12345",
        )
        # The context manager runs the app lifespan, which closes pooled SQLite connections
        # before the temporary directory is removed (required on Windows).
        with TestClient(create_app(settings)) as client:
            headers = {"X-API-Key": settings.api_key}
            response = client.post(
                "/v1/accounts",
                headers=headers,
                json={"account_id": "ng_latency_account", "display_name": "Latency Account"},
            )
            response.raise_for_status()
            start = datetime(2026, 1, 1, tzinfo=UTC)
            for index in range(args.warmup):
                response = client.post(
                    "/v1/events/score",
                    headers=headers,
                    json=event_payload(index, start + timedelta(minutes=index), "warmup"),
                )
                response.raise_for_status()

            timings: list[float] = []
            for index in range(args.requests):
                started = perf_counter()
                response = client.post(
                    "/v1/events/score",
                    headers=headers,
                    json=event_payload(
                        index,
                        start + timedelta(hours=2, minutes=index),
                        "measured",
                    ),
                )
                timings.append((perf_counter() - started) * 1_000)
                response.raise_for_status()


    values = np.asarray(timings)
    report = {
        "scope": "warm sequential FastAPI request including feature retrieval, model, policy, persistence, and audit",
        "requests": args.requests,
        "history_events_at_start": args.warmup,
        "p50_ms": round(float(np.percentile(values, 50)), 3),
        "p95_ms": round(float(np.percentile(values, 95)), 3),
        "p99_ms": round(float(np.percentile(values, 99)), 3),
        "max_ms": round(float(values.max()), 3),
        "under_one_second": bool(values.max() < 1_000),
        "production_caveat": "Run a distributed load test against the production feature store before launch.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"wrote={args.output}")


if __name__ == "__main__":
    main()
