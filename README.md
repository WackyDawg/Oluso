# Olùṣọ́ ATO

An explainable, defence-in-depth account-takeover platform designed for Nigerian mobile-money **app, USSD, and agency-banking** channels. Olùṣọ́ maintains customer, recipient, agent-terminal, risk-window, channel, calendar and campaign intelligence; separates risk from confidence; and converts evidence into reversible responses governed by a **Regret Budget**.

This is a clean-room implementation created for the challenge **“Spotting Account Takeover From Behaviour.”** It does not copy code or model artifacts from the public repositories used during competitive research.

## What is implemented

### v1.4 release assurance and honest-model evaluation

- Environment-list parsing is defined once at the runtime boundary and accepts canonical JSON arrays or shell-friendly comma-separated values.
- The checked-in `.env.example` and Docker Compose values use canonical JSON; an extracted-package smoke test copies the example to `.env`, boots the actual API and requires `/health` to return 200.
- Confirmed recipient reputation and transaction-type flags are excluded from population-model training, while remaining available to the transparent post-model policy where appropriate.
- The corpus adds groomed-recipient takeovers and legitimate recovery, failed-login retry and community-cooperative network lookalikes.
- Perfect synthetic ranking is now a failing release condition: model-only ROC-AUC is 0.9729 and fused ROC-AUC is 0.9611, with no single feature above 0.9386 separation AUC.
- A separate account-disjoint evaluation uses 450 training and 150 test customers with zero overlap; fused ROC-AUC is 0.9553 and customer-confirmation recall is 83.33%.
- Transfer-only metrics, Brier score, expected calibration error, score-range diagnostics and explicit low-and-slow failures are included rather than presenting perfect synthetic accuracy.

### v1.3 OlusoMesh Private Fraud-Sketch Exchange

- Cross-bank sharing of compact recipient, attested agent-terminal and categorical campaign indicators without sharing customer records or raw identifiers.
- Seven-day rotating HMAC indicator tokens and separately tokenised institutions; API responses never disclose either token.
- Institution-specific signed reports, freshness checks, approved evidence classes, replay nonces, issuer allow-list and hourly poisoning limits.
- Time-decayed aggregation with one-bank observe-only treatment and independent-institution counting.
- A strict local-corroboration ceiling: shared evidence alone can only monitor; corroborated evidence can contribute a reversible delay, not a hold.
- Signed 24-hour Fraud-Sketch Capsules preserve discounted, explicitly lower-confidence intelligence during consortium outages.
- Issuer-signed revocation, expiry, audit-chain recording and immediate cached-aggregate correction.
- A working chronological proof covering baseline, one/two institutions, uncorroborated and corroborated decisions, outage cache, legitimate biller, signature tampering, raw-value storage check and appeal-driven revocation.
- Honest production boundary: the prototype is privacy-reduced; VOPRF/PSI, HSM keys and formal consortium governance remain deployment requirements.

### v1.2 Agent-Terminal Integrity Twin

- A separate, causal risk lens for the **agent terminal itself**, rather than treating every agency transaction only as customer behaviour.
- Gateway-attested, tokenised agent and terminal references; customer devices cannot self-assert trusted terminal status.
- Cross-customer terminal velocity, recipient concentration, first-time-recipient ratio, failed-authentication ratio, registered-location mismatch, shift mismatch and terminal-age context.
- A compound campaign rule that requires cross-customer activity plus suspicious evidence, so ordinary queue volume at a busy market agent is not treated as fraud.
- Feedback propagation across affected accounts: one independent victim creates monitoring, two create an elevated security floor, and three quarantine the terminal pending review.
- Decaying, tenant-bound terminal reputation, independent second-approver control, analyst status endpoint and hash-chained reputation updates.
- Power-outage integration: unavailable terminal intelligence reduces decision confidence and is listed explicitly; missing evidence never becomes evidence of safety.
- A live proof showing a legitimate busy terminal allowed at 0.086 risk, a compromised terminal delayed at 0.740, quarantine after three independent victims, and an unattested forged claim ignored.

### v1.1 outage resilience layer

- A signed-heartbeat **GridAware Resilience Controller** with `online`, `degraded`, `isolated`, and `reconciling` states.
- An expiring, HMAC-signed **Edge Decision Capsule** binding the approved model hash/version and policy version.
- An **Outage Confidence Envelope** that lists unavailable evidence and reduces certainty without lowering the fraud score.
- A conservative **Offline Safety Envelope**: ordinary known payments may be monitored, unusual payments require confirmation, and a disconnected payment rail never reports settlement.
- A tenant-scoped, tamper-evident **Store-and-Forward Journal** preserving original timestamps and event/decision digests.
- Integrity-gated, idempotent reconciliation that re-scores queued events, records score changes and performs zero automatic settlements.
- A customer-safe outage receipt stating that no money moved and providing an `OFF-...` reference.
- An executable outage drill, role-separated API controls and dashboard showing mode, confidence, queue depth and journal integrity.

### v1.0 operational and governance layer

- **Safe Learning Firewall:** a current “safe” event waits 24 hours before teaching the twin; later fraud feedback revokes it and rebuilds the profile.
- **Campaign DNA:** privacy-reduced multi-stage patterns propagate across distinct accounts, with a three-stage eligibility guard against ordinary high-volume behaviour.
- **Exact causal replay:** event, feature, model, policy and cutoff digests reproduce each recorded decision envelope.
- **Enforced transaction lifecycle:** validated, idempotent authorize/hold/release/settle/cancel transitions plus an outbox event.
- **Privacy-reduced consortium intelligence:** HMAC recipient tokens require reports from at least two independent institutions before risk is raised.
- **Analyst governance:** prioritised cases, deterministic random low-risk audits, appeals, and independent second approval for strengthened recipient reputation.
- **Role and tenant isolation:** distinct integration, analyst, auditor and admin credentials with tenant-bound account, event, graph and decision access.
- **Policy/model governance:** non-mutating threshold simulation, version-bound provenance, signed registry summary, reference-window score/feature/action drift with a retraining recommendation, named fusion constants and security-floor rules (`oluso.scoring.SECURITY_FLOOR_RULES`, `oluso.policy.POLICY_THRESHOLDS`) and honest equity scope.
- **Privacy operations:** queued export/delete work and conservative two-channel profile succession after a verified device or SIM change.
- **Operational readiness evidence:** security headers, size/rate limits, Prometheus output, CycloneDX SBOM, hardened containers, CI security jobs, concurrent load evidence and verified backup/restore.

### Fraud intelligence layers

- Server-calculated behavioural profiles; callers cannot supply their own averages.
- App, USSD, web, and agent event channels.
- A channel-aware **Graceful Degradation Ladder**: rich app behaviour, USSD-gateway behaviour, agent-network behaviour, or core-banking fallback.
- Amount, balance-drain, recipient, device, SIM, IP, location, velocity, recovery, failed-authentication, and interaction-rhythm signals.
- Optional typed-versus-pasted, keystroke-cadence, phone-handling, and navigation-path signals.
- Hybrid scoring: calibrated Random Forest population model plus an interpretable personal anomaly scorer.
- Confidence-aware cold-start behaviour.
- Shared-device tolerance.
- Verified SIM-replacement mitigation; a legitimate SIM change is not treated like an unverified SIM swap.
- A recipient-side **Mule Graph Twin** that detects many first-time senders followed by rapid cash-out, while requiring cash-out evidence so popular merchants are not mislabeled.
- An **Agent-Terminal Integrity Twin** that detects one compromised agency endpoint harming several customers, while protecting legitimate high-throughput agents.
- A separate **Decision Confidence Envelope** that says how well-supported the risk score is; a low-risk/low-confidence cold start is not presented as “known safe.”
- A **Cross-Channel Transition Twin** that recognises new-device app enrolment followed by an unusual USSD hand-off as one attack sequence.
- A feedback-driven, tokenised **Recipient Reputation Loop**: one confirmed case raises monitoring across accounts; two independent victims activate a stronger floor; reports decay and expire after 90 days.
- An **OlusoMesh Private Fraud-Sketch Exchange** that shares rotating recipient, attested-terminal and campaign tokens across institutions, with signed issuers, poisoning controls, revocation, outage cache and local-action ceilings.
- A **Calendar Rhythm Twin** that recognises an established day-of-month, recipient and amount pattern after three prior monthly cycles.
- A decaying **Account Risk Window** that turns failed authentication, recovery, PIN reset, and attested SIM-change precursors into time-varying hazard state.
- Consent-gated, device-attested **coercion protection** that can privately pause an in-call or screen-shared payment without accusing the customer.
- Counterfactual recourse: each interrupted decision returns safe ways to clear it, an expected clearance time, and the official channel to use.
- An adaptive-attacker harness that searches 2,688 valid raw transaction variants for the largest below-threshold evasion, then tests graph and precursor mitigations.
- Optional attested telco-assurance envelope for USSD and feature phones: SIM activation age,
  subscriber/card identity change, repeat replacements, previous tenure, and OTP proximity/geography.
- Telco fields are ignored unless a trusted gateway attests them; raw IMSI/ICCID values are never required.
- Human-readable reason codes and score breakdowns.
- One customer-ready explanation sentence for every approval, challenge, delay, or hold.
- Reversible actions: monitoring, trusted-channel confirmation, settlement delay, or temporary hold.
- A soft 30-day Regret Budget limiting repeated customer disruption while preserving critical overrides.
- A **Personalised Friction Optimizer** comparing expected fraud exposure with the customer cost of monitoring, confirmation, delay and hold; it penalises repeated, USSD and low-confidence friction.
- Suspicious events cannot silently teach themselves into the trusted behavioural baseline.
- Analyst feedback endpoint.
- SHA-256 chained audit log with an integrity-verification endpoint.
- Model, training-dataset, and feature-schema hashes for reproducible evidence provenance.
- FastAPI service, Streamlit demonstration dashboard, synthetic training workflow, tests, and Docker Compose.
- Linked synthetic account, raw session/event, and derived-feature datasets generated through the production feature engine.
- End-to-end policy evaluation, low-prevalence stress testing, hard-negative cohort reporting, and a reproducible latency benchmark.

## Architecture

```text
App / USSD / Agent events
           │
           ▼
Authenticated FastAPI ingestion
           │
           ├── Historical event store ──► Sender twin + risk window
           ├── Cross-account event view ─► Recipient mule graph
           │                                      │
           ├── Population ML model ◄──── Server-side feature engine
           │                                      │
           └── Transparent anomaly rules ◄────────┘
                              │
                              ▼
              Risk fusion + separate decision confidence
                              │
                              ▼
       Friction-cost policy + Regret Budget + recourse
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
       Risk decision API               SHA-256 audit chain
```

<img src="https://res.cloudinary.com/dfcmtuhjv/image/upload/v1790023302/diagram_1_b47nqa.png" alt="gitdiagram" loading="eager" width="full" height="full"/>

See [Private Fraud-Sketch Exchange](docs/PRIVATE_FRAUD_SKETCH_EXCHANGE.md), [Outage Resilience](docs/OUTAGE_RESILIENCE.md), [v1 Platform Controls](docs/V1_PLATFORM.md), [Security Architecture](docs/SECURITY_ARCHITECTURE.md), [Model Governance](docs/MODEL_GOVERNANCE.md), [Privacy and Compliance](docs/PRIVACY_AND_COMPLIANCE.md), [Operations Runbook](docs/OPERATIONS_RUNBOOK.md), [Control Traceability](docs/CONTROL_TRACEABILITY.md), [Test Strategy](docs/TEST_STRATEGY.md), [API Reference](docs/API_REFERENCE.md), [Architecture](docs/ARCHITECTURE.md), [Synthetic Data Methodology](docs/SYNTHETIC_DATA.md), [End-to-End Evaluation](docs/EVALUATION.md), and [Threat Model](docs/THREAT_MODEL.md).

## Quick start

### Local installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,dashboard]'
cp .env.example .env
```

The repository contains a development model artifact. To regenerate it:

```bash
python scripts/generate_synthetic.py --rows 30000
python scripts/train_model.py
python scripts/evaluate_system.py
python scripts/evaluate_robustness.py
python scripts/benchmark_latency.py --requests 30
python scripts/demo_v5_features.py
python scripts/demo_v1_platform.py
python scripts/demo_outage_resilience.py
python scripts/demo_agent_terminal.py
python scripts/demo_fraud_sketch_exchange.py
python scripts/load_test.py --requests 100 --workers 8
python scripts/generate_sbom.py
python scripts/release_smoke_test.py .
```

Start the API:

```bash
uvicorn app:app --reload --port 8000
```

Open the OpenAPI interface at `http://localhost:8000/docs`.

In another terminal, start the demonstration dashboard:

```bash
source .venv/bin/activate
streamlit run dashboard/app.py --server.port 8501
```

Then open `http://localhost:8501`. Use the demo API key from `.env`; the development default is `dev-only-change-me` and must never be used in production.

### Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- API: `http://localhost:8000/docs`
- Dashboard: `http://localhost:8501`

## Five-minute demo

The quickest terminal demonstration creates a mature normal profile and then submits a simulated SIM-swap balance-drain event:

```bash
python scripts/seed_demo.py
```

Expected outcome: a critical score, a reversible two-hour hold, trusted-channel confirmation, analyst review, explanations, and an audit hash. See the full [Demo Script](docs/DEMO_SCRIPT.md).

## API example

Create an account:

```bash
curl -X POST http://localhost:8000/v1/accounts \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-only-change-me' \
  -d '{
    "account_id": "customer_001",
    "display_name": "Demo Customer",
    "shared_device_allowed": false,
    "regret_limit_30d": 3,
    "trusted_contact_masked": "+234 *** *** 104"
  }'
```

Score a transaction:

```bash
curl -X POST http://localhost:8000/v1/events/score \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-only-change-me' \
  -d '{
    "event_id": "event_000001",
    "account_id": "customer_001",
    "occurred_at": "2026-08-23T10:30:00+01:00",
    "event_type": "transfer",
    "channel": "ussd",
    "amount": 48000,
    "available_balance_before": 52000,
    "recipient_id": "recipient_new",
    "device_id": "device_unknown",
    "sim_id": "sim_unknown",
    "ip_prefix": "197.210.44.0/24",
    "latitude": 6.5244,
    "longitude": 3.3792,
    "interaction_ms": 2400,
    "menu_depth": 7
  }'
```

## Main endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Model and audit health; no authentication required |
| `POST` | `/v1/accounts` | Register an account and its UX policy |
| `POST` | `/v1/events/score` | Store, feature, score, explain, and audit an event |
| `GET` | `/v1/accounts/{id}/profile` | View a privacy-reduced behavioural twin |
| `GET` | `/v1/accounts/{id}/decisions` | Retrieve recent decisions |
| `POST` | `/v1/decisions/{id}/feedback` | Record analyst ground truth |
| `GET` | `/v1/agent-terminals/{token}/status` | Read tokenised terminal reputation; analyst-only |
| `GET` | `/v1/audit/verify` | Verify the local append-only hash chain |
| `GET` | `/v1/model` | Inspect model version, artifact hash, and evaluation metrics |
| `GET` | `/v1/metrics` | Operational decision counts |
| `GET` | `/v1/decisions/{id}/replay` | Verify exact decision provenance |
| `POST` | `/v1/events/{id}/lifecycle` | Apply an idempotent settlement-state transition |
| `GET` | `/v1/cases` | Retrieve the risk-prioritised analyst queue |
| `POST` | `/v1/consortium/reports` | Add privacy-reduced independent recipient intelligence |
| `POST` | `/v1/fraud-sketch/reports` | Add an institution-signed rotating private fraud sketch |
| `POST` | `/v1/fraud-sketch/reports/{id}/revoke` | Correct an issuer-owned sketch report |
| `GET` | `/v1/fraud-sketch/status` | Inspect an aggregate without returning shared tokens |
| `POST` | `/v1/policy/simulate` | Compare thresholds without changing live policy |
| `GET` | `/v1/governance/drift` | Reference-window PSI drift on scores, monitored features and action mix, with a retraining recommendation |
| `GET` | `/v1/governance/equity` | Read scoped intervention-distribution evidence |
| `POST` | `/v1/privacy/requests` | Queue an audited export or deletion request |
| `POST` | `/v1/audit/anchor` | Sign the current audit-chain head |

All protected endpoints require a role-scoped `X-API-Key` and allowed `X-Tenant-ID`. Replace demonstration keys with an organisation identity provider, workload identity and mTLS for production.

## Behavioural features

The runtime derives features from previously observed events before writing the new event into the profile:

- Robust deviation from median transaction amount.
- Share of balance being moved.
- Hour-of-day deviation.
- Recipient novelty and rarity.
- Recipient sender diversity, first-time-sender ratio, recent inflow, and rapid cash-out ratio.
- Tokenised recipient confirmed-fraud score, independent reporting-account count, decay, and watchlist coverage.
- Device, SIM, IP, and channel novelty.
- Channel-transition novelty, cross-channel activity in 15 minutes, new-device/channel enrolment, app-to-USSD hand-off, and device mismatch.
- Five-minute and one-hour transaction velocity.
- Failed authentication in the previous 24 hours.
- PIN-reset or recovery activity in the previous 72 hours.
- A decaying precursor hazard score and remaining risk-window duration.
- Geographical travel velocity.
- App/USSD milliseconds-per-menu-step deviation.
- Typed-versus-pasted behaviour and keystroke-cadence deviation.
- Device-handling and navigation-path deviation when an app or gateway exposes them.
- Day-of-month deviation, recurring recipient/amount match, and calendar-history confidence.
- Consent-gated call overlap, screen sharing, recipient edits, confirmation backtracks, and on-device coercion score.
- Verified SIM-replacement context, gateway-attested privacy-reduced SIM-lifecycle indicators,
  and channel-specific evidence coverage.
- Profile confidence, shared-device status, and channel context.
- Gateway-attested agent-terminal customer diversity, recipient concentration, failed-authentication ratio, value velocity, location/shift mismatch, novelty and confirmed reputation.

High-risk or interrupted events are retained for investigation but marked ineligible to update the trusted baseline. This prevents an attacker from gradually normalising malicious behaviour.

## Development model and live-policy results

The included model was trained on 30,000 raw-derived synthetic Nigerian transactions using a chronological 65%/17%/18% split. The dataset contains 750 behavioural twins. On the 5,400-event held-out segment, the exact live fusion and policy produced:

| Live response | Recall | Precision | False-positive rate | False alerts |
|---|---:|---:|---:|---:|
| Monitor or stronger | 93.18% | 85.42% | 0.1307% | 7 / 5,356 normal events |
| Customer confirmation or stronger | 90.91% | 95.24% | 0.0373% | 2 / 5,356 normal events |
| Settlement delay or hold | 90.91% | 95.24% | 0.0373% | 2 / 5,356 normal events |
| Two-hour hold and review | 79.55% | 97.22% | 0.0187% | 1 / 5,356 normal events |

At the customer-confirmation threshold, 40 of 44 held-out takeovers were detected (95% stratified bootstrap interval 81.8%–97.7%; Wilson 78.8%–96.4%). With 44 positives the interval, not the point, is the honest claim. A component ablation at the same threshold shows the calibrated model alone at 40/44 with 2 false alerts, the transparent anomaly scorer alone at 41/44 but 112 false alerts, and the named security floors alone at 32/44 with none; no detection required a floor, so the floors act as severity guarantees rather than the source of recall. See the uncertainty, ablation and attribution tables in [End-to-End Evaluation](docs/EVALUATION.md). All 7 held-out agency social-engineering attacks were detected, while 60/60 deliberately busy legitimate-agent payments produced no intervention. Three deliberately subtle low-and-slow events were missed, and one of four remote-control USSD events was missed. Popular merchants, recurring monthly payments, verified SIM replacements, shared family phones and other hard negatives remain explicitly measured. These small scenario counts and designed simulation remain important limitations.

The warm sequential and warmed concurrent API benchmarks are regenerated from the exact packaged runtime: 32.5 ms p50 / 45.8 ms p95 / 183.5 ms p99 sequential over 100 requests, and 22.6 requests/s with 477.9 ms p99 across 100 successful requests with eight workers. The gains over the earlier build come from pooling SQLite connections (a scored event touches the store about forty times) and from a verified fast inference path that walks the calibrated forest's fitted trees directly instead of paying sklearn's per-tree input validation for a single row; the path is enabled only when it reproduces `predict_proba` to 1e-6 on a probe set, so no probability, threshold or metric changed. Remaining concurrency cost is SQLite's single writer plus the audit hash chain, which must serialise. The exchange-specific proof also reports signed-ingestion latency and cached-outage behaviour. These laptop measurements expose prototype behaviour, not production availability. See [End-to-End Evaluation](docs/EVALUATION.md), [Private Fraud-Sketch Exchange](docs/PRIVATE_FRAUD_SKETCH_EXCHANGE.md), [Outage Resilience](docs/OUTAGE_RESILIENCE.md), [Agent-Terminal Integrity](docs/AGENT_TERMINAL_INTEGRITY.md), and machine-readable reports in `artifacts/`.

These values verify that the pipeline works on its designed simulation. **They are not evidence of production performance.** The evaluation also projects precision and alerts per 10,000 at 0.1%, 0.5%, and 1% fraud prevalence rather than hiding the base-rate problem. Real deployment requires consented representative data, demographic and channel fairness tests, attack replay, drift monitoring, threshold governance, distributed load testing, and independent validation.

## Validation

```bash
pytest
ruff check .
```

Current validation includes **64 tests with a coverage gate above 85%** (91% measured). It covers the original feature, graph, confidence, calendar, coercion, recourse and policy behaviour plus safe learning, campaign safeguards, consortium independence, exact replay, lifecycle idempotency, analyst governance, tenant isolation, outage safety and reconciliation. Configuration contract tests load the actual `.env.example`, exercise CSV compatibility and reject empty tenant lists. The release smoke test boots a clean staged copy, while the robustness gate rejects perfect synthetic ranking or any near-deterministic single feature. Fraud-sketch tests prove signature and replay rejection, issuer allow-listing, rotating token storage, independent-institution counting, local-action ceilings, attested-terminal/campaign matching, signed outage cache, revocation, legitimate-biller safety and analyst-only APIs.

## Production boundaries

- Do not allow clients to submit historical aggregates; compute them from trusted event streams.
- Hash or tokenize device, SIM, recipient, and network identifiers before persistence.
- Treat the v1.3 exchange as privacy-reduced; use VOPRF/PSI or secure aggregation, HSM-backed rotation and formal correction/appeal governance before a real multi-bank deployment.
- Store precise location only when legally justified; prefer coarse geohashes.
- Load model artifacts only from a signed internal registry. `joblib`/pickle artifacts are executable formats.
- Replace SQLite with an encrypted managed datastore and transaction-safe streaming feature store at scale.
- The MVP uses striped account locks so unrelated customers can score concurrently, but multi-replica deployments still require distributed per-account ordering.
- Replace the demo API key with short-lived service credentials, mTLS, rate limiting, and least-privilege scopes.
- The audit hash chain detects alteration but does not prevent deletion of the entire database. Periodically anchor its head in an independent transparency service if required.
- Never treat an ML score as proof of guilt. The policy engine produces reversible safeguards and human-review signals.

## Project structure

```text
.
├── src/oluso/            Library code
│   ├── api.py            FastAPI app factory, RBAC, rate limiting, lifespan
│   ├── service.py        Scoring orchestration, governance reports, replay, reconciliation
│   ├── features.py       FeatureEngine, risk windows, MODEL_EXCLUDED_FEATURES
│   ├── scoring.py        Anomaly scorer, named security floors, fusion, ModelBundle (+ fast path)
│   ├── policy.py         POLICY_THRESHOLDS, expected-cost action selection, regret budget
│   ├── evaluation.py     Intervals, ablation, attribution, leakage audit (used by scripts/)
│   ├── storage.py        SQLite repository (WAL, pooled connections, indexes)
│   ├── audit.py          Hash-chained audit log
│   ├── resilience.py     Outage modes, signed heartbeats/capsules, offline journal
│   ├── fraud_sketch.py   Private cross-institution fraud-sketch tokens and signatures
│   ├── network.py / agent.py / profile.py / platform.py / schemas.py / config.py / telemetry.py
├── tests/                pytest suite (64 tests; CI gate 85% coverage)
├── scripts/              generate_synthetic, train_model, evaluate_system, evaluate_robustness,
│                         adaptive_attack_search, benchmark_latency, load_test, demo_*, release_smoke_test
├── tools/                build_technical_writeup, build_demo_video, package_submission
├── dashboard/            Streamlit investigator console
├── docs/                 Architecture, model card, governance, threat model, runbooks (single source of truth)
├── artifacts/            Machine-readable evidence produced by scripts/ (see artifacts/README.md)
├── data/                 Synthetic corpus (see data/README.md)
├── models/               Versioned model artifact (see models/README.md)
├── submission/           Hackathon deliverables; dist/ is generated (see submission/README.md)
├── app.py                `uvicorn app:app` entry point
├── Makefile              Developer tasks (`make help`)
└── .github/              CI, CodeQL, Dependabot, PR and issue templates
```

Development workflow, conventions and the evidence-regeneration rules are in [CONTRIBUTING.md](CONTRIBUTING.md);
release history is in [CHANGELOG.md](CHANGELOG.md).

## Licence

MIT. See [LICENSE](LICENSE).
