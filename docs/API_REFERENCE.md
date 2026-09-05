# API reference and roles

All protected requests use `X-API-Key` and `X-Tenant-ID`. The development roles are integration, analyst, auditor and admin; production must map them to short-lived organisational identities.

| Role | Selected endpoints |
|---|---|
| Integration | create account, score event, read profile/decisions, create appeal, queue privacy request |
| Analyst | feedback, review cases, lifecycle transition, signed fraud-sketch report/revocation, consortium compatibility report, profile succession, tokenised agent-terminal status |
| Auditor | audit verify/anchor, decision replay, metrics, model registry, drift, equity, policy simulation, telemetry, outage journal verification and reconciliation |
| Admin | Demonstration break-glass access plus signed outage heartbeat/simulation control |

Outage endpoints are `GET /v1/resilience/status`, admin-only `POST /v1/resilience/heartbeat`, non-production admin-only `POST /v1/resilience/simulate`, auditor-only `GET /v1/resilience/journal/verify`, and auditor-only `POST /v1/resilience/reconcile`. Heartbeats require a fresh timezone-aware timestamp, unique nonce and HMAC signature. Reconciliation requires restored dependencies and a valid journal.

Other platform endpoints are `GET /v1/decisions/{id}/replay`, `POST /v1/events/{id}/lifecycle`, `GET /v1/cases`, `POST /v1/decisions/{id}/appeals`, `POST /v1/consortium/reports` (deprecated compatibility), `POST /v1/fraud-sketch/reports`, `POST /v1/fraud-sketch/reports/{id}/revoke`, `GET /v1/fraud-sketch/status`, `POST /v1/policy/simulate`, `GET /v1/governance/drift`, `GET /v1/governance/equity`, `POST /v1/privacy/requests`, `POST /v1/profiles/succession`, `POST /v1/audit/anchor`, `GET /v1/observability`, and Prometheus `GET /metrics`.

Fraud-sketch reports contain a report ID, enrolled institution ID, indicator type (`recipient`, `agent_terminal` or `campaign`), source value, confidence, approved evidence class, timezone-aware observation time, TTL, unique nonce and 64-character HMAC signature. The value is used only to derive an epoch token and is not persisted in shared tables. The response returns counts, score, expiry and status, never the indicator or institution token. Revocation is separately signed by the original issuer. See `scripts/demo_fraud_sketch_exchange.py` for executable signing examples.

Agent-channel score requests may include a gateway-attested `agent_assurance` envelope containing opaque `agent_token` and `terminal_token`, registered coordinates, approved shift hours and terminal age. The envelope is rejected on non-agent channels and ignored when unattested. `GET /v1/agent-terminals/{terminal_token}/status` is analyst-only and returns a tokenised terminal reference, decaying score, report/account counts, status, quarantine state and expiry; it never returns the caller-supplied raw token.

OpenAPI at `/docs` is the executable field-level contract.
