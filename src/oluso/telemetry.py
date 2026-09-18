from __future__ import annotations

import threading
from collections import defaultdict
from time import perf_counter
from typing import Any


class Telemetry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._latencies: list[float] = []

    def increment(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[key] += amount

    def observe_latency(self, seconds: float) -> None:
        with self._lock:
            self._latencies.append(seconds * 1000)
            self._latencies = self._latencies[-5000:]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            values = sorted(self._latencies)
            percentile = lambda p: values[min(len(values) - 1, int(len(values) * p))] if values else 0.0
            return {"counters": dict(self._counters), "latency_ms": {
                "count": len(values), "p50": round(percentile(.50), 3),
                "p95": round(percentile(.95), 3), "p99": round(percentile(.99), 3),
            }}

    def prometheus(self) -> str:
        data = self.snapshot()
        lines = [f'oluso_events_total{{type="{key}"}} {value}' for key, value in data["counters"].items()]
        lines += [f'oluso_scoring_latency_ms{{quantile="{key[1:]}"}} {value}' for key, value in data["latency_ms"].items() if key.startswith("p")]
        return "\n".join(lines) + "\n"


class timed:
    def __init__(self, telemetry: Telemetry):
        self.telemetry = telemetry

    def __enter__(self) -> None:
        self.started = perf_counter()

    def __exit__(self, *_: object) -> None:
        self.telemetry.observe_latency(perf_counter() - self.started)
