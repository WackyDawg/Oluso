# Security architecture

## Trust boundaries

The integration role may create accounts, score events, read profiles, request appeals and queue privacy work. The analyst role handles feedback, cases, lifecycle decisions, signed fraud-sketch reports/revocations, compatibility consortium reports and profile succession. The auditor role verifies the audit chain, replays decisions, runs policy simulations, reads drift/equity/telemetry and anchors the chain. The admin role is a demonstration break-glass identity.

Every account, event and decision is bound to an allowed tenant. Cross-account graph and campaign queries are tenant scoped. AegisMesh is a separate consortium boundary: source values become seven-day HMAC tokens, institutions are separately tokenised, and the API never returns either. Report/revocation signatures use issuer-specific prototype keys. Shared evidence cannot exceed monitoring without local corroboration and cannot independently justify a hold.

## Evidence trust

Telco and coercion evidence only affects risk when attested. If `metadata.gateway_observed_at` is older than the configured freshness limit, attestation is stripped before feature extraction. Callers cannot submit profile aggregates, campaign counts, watchlist scores or model features.

## Abuse controls

- Sliding-window request limiting and a request-size ceiling.
- Strict Pydantic validation and idempotent lifecycle keys.
- Security response headers and a no-store cache policy.
- Dual approval when a second fraud confirmation would strengthen shared recipient reputation.
- Institution allow-list, per-issuer signature, freshness, replay nonce, evidence class, confidence floor, hourly quota, expiry and signed revocation for shared fraud sketches.
- Random low-risk review samples to detect systematic misses.
- Non-root, read-only containers with all Linux capabilities dropped.
- Dependency audit, static analysis, CodeQL, coverage and SBOM jobs in CI.

## Production substitutions

Static keys, SQLite, the local outbox and HMAC token/signature adapters are reference implementations. A bank deployment must use workload identity, mTLS, HSM-backed keys, an encrypted high-availability database, durable streaming, signed model registry, network segmentation, centralized logs, formal key rotation and independent penetration testing. A real consortium additionally needs VOPRF/PSI or secure aggregation where justified, operator separation, participation rules, correction/appeal SLAs and privacy leakage testing.
