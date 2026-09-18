# Power and Network Outage Resilience

Oluso v1.1 treats unavailable fraud intelligence, unavailable scoring runtime, and an unavailable
payment rail as different failures. Missing evidence is never interpreted as evidence that a payment
is safe. The implementation follows a four-state operating model:

| Mode | Trigger | Permitted behaviour |
|---|---|---|
| `online` | All trusted services available | Normal scoring, policy and quarantined learning |
| `degraded` | Core bank reachable; one or more intelligence/runtime services unavailable | Signed local capsule, reduced confidence, monitored ordinary activity and confirmation for unusual payments |
| `isolated` | Core payment connection unavailable | Local advisory scoring only; monetary instructions remain held with a connectivity-safe reference and no settlement claim |
| `reconciling` | Trusted services return after an outage | Verify the journal, re-score every pending event, record score changes and never auto-settle |

## Signed heartbeat and edge capsule

The admin-only heartbeat endpoint accepts dependency health only when the payload has a fresh UTC
timestamp, a unique nonce and a valid HMAC-SHA-256 signature. Replayed, stale or modified heartbeats
are rejected. The edge capsule binds tenant, model version/hash, policy version, issue time and expiry.
An expired or modified capsule forces confidence to at most 25 percent during an outage.

The v1.3 exchange also maintains indicator-specific signed Fraud-Sketch Capsules. When the consortium is unavailable, a valid capsule is labelled `signed_cache`, its exchange score is discounted by 15 percent and its confidence by 25 percent. Expired or altered capsules contribute nothing. This preserves bounded cross-bank warning during a network cut without pretending cached evidence is fresh.

The development HMAC is a demonstrable trust boundary, not production key management. A bank pilot
must use workload identity, mTLS, a hardware-backed signing key, rotation and independent health
sources.

## Outage Confidence Envelope and Safety Envelope

Every decision returns the operating mode, unavailable sources, evidence freshness, capsule status,
confidence multiplier, whether the safety envelope was applied and an optional offline reference.
Outage activity cannot update the behavioural baseline. In degraded mode, an unusual recipient,
recovery precursor, simultaneous new device/SIM or major balance drain requires a reversible trusted
confirmation even when the base policy would be milder. In isolated mode, every monetary instruction
is delayed or held. The customer message says explicitly that no money has moved.

## Tamper-evident store-and-forward journal

Each outage decision is appended to a tenant-scoped SHA-256 chain containing the original occurrence
time, event and decision references, mode, score, action and event digest. Changing any stored payload
breaks verification at that entry. Events keep their original time separately from reconciliation
time. The journal is local prototype evidence; production requires encryption at rest, durable
replication, bounded retention and independently witnessed chain heads.

## Recovery and exactly-once safety

Recovery is deliberately gated. Restored services first move the controller to `reconciling`.
Reconciliation stops if journal integrity fails. Otherwise, pending events are re-scored without
inserting a second event, teaching the profile or issuing a settlement transition. Each journal row
can move from pending to reconciled once. A repeated reconciliation returns `already_reconciled` and
the measured duplicate-action count remains zero.

The recovery-storm controller drains a caller-bounded batch in descending risk order, preserving
original sequence as the tie-breaker. It exposes remaining depth and opens a circuit breaker after a
bounded failure budget, leaving unprocessed rows pending for investigation rather than retrying in a
tight loop.

The prototype does not claim that queued transfer intent is a completed bank transfer. A real payment
connector must use the existing lifecycle idempotency key, a unique rail authorization token and the
bank ledger as the settlement source of truth.

## Demonstration and evidence

Run:

```bash
python scripts/demo_outage_resilience.py
```

The machine-readable `artifacts/outage_resilience.json` records state transitions, signed capsule
validity, confidence degradation, customer-safe isolated handling, deliberate journal tampering,
successful exact restoration, reconciliation counts, duplicate actions, outage-detection time,
recovery time and audit-chain validity. Automated tests independently cover signature rejection,
nonce replay, learning freeze, safety-envelope policy, isolated payment handling, tamper detection,
reconciliation idempotency and role separation.

`artifacts/fraud_sketch_exchange.json` separately proves that a two-bank private aggregate remains available from a signed cache in degraded mode, with explicit confidence reduction and the same monitoring/local-corroboration ceilings.

This design is informed by NIST SP 800-34 contingency planning and the NIST Cybersecurity Framework
2.0 Recover outcomes. It remains a laptop prototype, not a certified bank business-continuity system.
