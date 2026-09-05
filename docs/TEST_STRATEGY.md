# Test and evidence strategy

The 64 automated tests cover unit rules, named security-floor attribution, bootstrap/Wilson interval helpers, component ablation, evidence-coverage leakage detection, reference-window drift, feature causality, response policy, recipient and agent-terminal graph safeguards, persistence, API authentication, role separation, tenant isolation, lifecycle idempotency, safe learning, de-learning, consortium independence, exact replay, appeals, privacy queues, profile succession, audit integrity, signed outage heartbeats, nonce replay, learning freeze, conservative degraded/isolated policy, journal tampering, bounded recovery and idempotent reconciliation. Three configuration-contract tests load the checked-in `.env.example`, retain CSV compatibility and reject an empty tenant allow-list. The CI coverage gate remains 85%.

The chronological held-out evaluation contains 5,400 events after training cutoff: 44 takeovers and 5,356 normal events. It reports thresholds independently so confirmation performance is not confused with automatic hold performance. Twelve hard-negative families include verified SIM replacement, legitimate recovery, failed-login retry, popular merchant, cooperative collection, recurring monthly payment, shared family phone, legitimate new phone, payday spending, domestic travel, emergency transfers and busy legitimate agent terminals.

Additional evidence:

- `adaptive_redteam.json`: 2,688 valid attacker variants and the best remaining evasion.
- `v1_platform_demo.json`: safe learning, retroactive de-learning, campaign propagation, consortium independence, exact replay, lifecycle cancellation, governance, telemetry and audit validity.
- `latency.json`: warm sequential full-API latency.
- `concurrent_load.json`: eight-worker SQLite stress evidence including failures.
- `coverage.json`: machine-readable code coverage.
- `sbom.cdx.json`: CycloneDX 1.5 dependency inventory.
- backup manifest: online backup hash and restore integrity check.
- `outage_resilience.json`: four-state transition proof, capsule validation, confidence degradation, customer-safe isolated handling, deliberate tamper detection and zero-duplicate recovery.
- `agent_terminal_demo.json`: busy-agent safeguard, live compound campaign, independent-victim reputation progression, quarantine, forged-claim rejection and audit integrity.
- `fraud_sketch_exchange.json`: chronological baseline, one/two institutions, corroboration ceiling, signed outage cache, legitimate-biller hard negative, signature tamper rejection, privacy-storage check, revocation, latency and audit integrity.
- `robustness.json`: perfect-separation release gate, top univariate separation audit and an account-disjoint test with zero customer overlap.

`scripts/release_smoke_test.py` stages either the source tree or packaged source ZIP into a clean temporary directory, copies `.env.example` to `.env`, imports the packaged application and requires a successful `/health` response. CI runs this test from the canonical template so configuration fixes cannot be lost during packaging.

The five focused agent-terminal tests verify a busy legitimate terminal, cross-customer compromise, feedback propagation, forged unattested evidence, analyst-only status access and three-victim quarantine. Synthetic cohort checks separately measure `agent_social_engineering` attack recall and `busy_agent_merchant_payment` customer interruption.

Six fraud-sketch tests verify rotating private storage, independent-institution aggregation, signature tamper rejection, nonce replay, issuer allow-listing, action ceilings, signed outage cache, revocation, analyst RBAC, and recipient/attested-terminal/campaign indicator types.

These are prototype measurements on synthetic data and one laptop environment. They are not production assurance.
