# Threat Model

## v1.3 private fraud-sketch additions

- **Dictionary or membership inference:** source values become seven-day HMAC tokens and are never returned, but the prototype is explicitly privacy-reduced because the token operator could test guesses. Production moves to VOPRF/PSI or secure aggregation with query controls.
- **Institution impersonation:** every report/revocation requires the enrolled institution's key, approved analyst role, fresh timestamp and canonical signature.
- **Replay:** single-use nonces and idempotent report IDs reject duplicate or conflicting content.
- **Poisoning/Sybil reports:** issuer allow-list, institution-specific keys, hourly quotas, evidence classes, minimum confidence, expiry and independent-institution counting constrain influence.
- **False cross-bank accusation:** one issuer and all uncorroborated matches are monitoring-only. Shared evidence cannot independently justify a hold; revocation and expiry immediately reduce the aggregate.
- **Outage cache tampering or staleness:** cached aggregates are signed, short lived, discounted and labelled; invalid/expired capsules contribute nothing and missing exchange evidence reduces confidence.
- **Cross-bank raw-data leakage:** shared tables contain rotating tokens and coarse metadata only; customer, transaction, SIM, device and terminal histories remain local.

## v1.2 agent-terminal additions

- **Forged terminal assurance:** agent-terminal fields have no effect unless the bank gateway attests the envelope; non-agent channels reject the envelope.
- **One compromised endpoint, many customers:** causal terminal aggregates detect cross-customer authentication failures and concentrated beneficiary flow.
- **Busy-agent false positive:** the campaign rule requires cross-customer diversity, concentration and suspicious corroboration; volume alone is insufficient.
- **Malicious terminal reputation report:** one victim produces monitoring only; independent victims and a second approver are required before elevation and quarantine.
- **Cross-tenant terminal disclosure:** reputation storage and lookup are tenant-bound; the analyst endpoint returns a tokenised reference rather than the supplied token.
- **Terminal intelligence outage:** missing agent evidence reduces decision confidence and invokes the outage safety envelope; it never reduces risk.

## v1.1 outage additions

- **Forged or replayed outage signal:** heartbeat payloads require HMAC verification, a fresh timestamp, a unique nonce and admin role.
- **Stale edge policy:** the signed capsule has an explicit expiry; an invalid capsule drives decision confidence to at most 25 percent.
- **Missing evidence treated as safe:** unavailable sources are named and confidence is reduced; unusual degraded payments receive a reversible safety floor.
- **False settlement during core outage:** isolated transactions remain held and the customer message says no money moved.
- **Offline profile poisoning:** every outage event is excluded from learning until restored evidence is reviewed.
- **Offline queue alteration:** each tenant has a SHA-256 store-and-forward chain; reconciliation stops at the first invalid entry.
- **Duplicate recovery processing:** pending rows reconcile once, re-scoring is non-mutating, and no automatic settlement is performed.

## v1.0 additions

- **Baseline poisoning:** provisionally safe events are quarantined; later fraud feedback revokes them and rebuilds the profile.
- **Cross-account campaign:** multi-stage signatures gain strength only across distinct accounts and never from an ordinary motif.
- **False watchlist escalation:** the second strengthening report needs an independent approver; consortium risk needs independent institutions.
- **Stale or forged gateway evidence:** unattested or stale evidence is ignored before feature extraction.
- **Cross-tenant disclosure:** account, event, decision, graph and campaign reads require tenant ownership.
- **Privilege abuse:** integration, analyst and auditor operations use separate roles; sensitive actions are chained into the audit log.
- **Settlement replay or race:** lifecycle transitions follow a state graph and require unique idempotency keys.
- **Model or policy substitution:** artifact/data/schema hashes, policy version, cutoff and replay digest are bound to every decision; the registry summary is signed.
- **Audit truncation:** the local chain detects modification, while the current head can be signed for independent anchoring. Complete database deletion still requires off-host monitoring and backups.
- **Denial of service:** rate, request-size and container controls reduce abuse, but distributed production protection is outside the laptop prototype.

## Protected assets

- Customer funds and ability to transact.
- Authentication and recovery integrity.
- Behavioural profiles and sensitive metadata.
- Risk decisions and analyst feedback.
- Model artifacts, thresholds, and policy configuration.
- Audit history.

## Primary adversaries

- Credential thief with valid username/PIN credentials.
- SIM-swap attacker.
- Social engineer using remote-access tooling.
- Money mule receiving drained funds.
- Malicious or compromised third-party integration.
- Insider attempting to alter risk history.
- Attacker probing the model to learn thresholds.
- Caller or remote helper coercing the genuine customer into making a payment.
- Patient attacker minimizing behavioural change while using a mule recipient.
- Compromised or malicious agency terminal touching several unrelated customers.

## Trust boundaries

1. Mobile/USSD channel to the financial institution.
2. Integration gateway to the scoring API.
3. API to event/profile database.
4. Scoring service to model artifact.
5. Decision service to settlement and case-management systems.
6. Analyst interface to feedback records.
7. Bank/agent gateway to attested terminal assurance and terminal registry.
8. Participating institution to the OlusoMesh sketch exchange and signed cache.

## Threats and implemented controls

| Threat | Control in this MVP | Production enhancement |
|---|---|---|
| Caller falsifies behavioural averages | Aggregates are calculated from server history | Signed event-stream provenance |
| Event replay | Unique event IDs and conflict response | Idempotency registry across regions |
| Attacker poisons their baseline | Interrupted/high-risk events are profile-ineligible | Confirmed-legitimate feedback gate and delayed enrolment |
| Malicious/incorrect analyst poisons recipient watchlist | One report causes monitoring only; strong floor needs two distinct accounts; 90-day decay | RBAC, dual approval, appeals, case-quality scoring and consortium governance |
| Guessing tokenised recipient identifiers | Prototype stores SHA-256 tokens rather than raw IDs | Use keyed HMAC/token vault, rotation and access separation |
| New-channel enrolment used before USSD drain | Ordered cross-channel transition features and compound floor | Bind enrolment to trusted-device confirmation and cooling-off policy |
| Thin history mistaken for safety | Separate decision confidence, missing-evidence reasons, no low-confidence automatic hold | OOD detection, abstention calibration and analyst queue |
| Shared family handset causes false positive | Per-account shared-device tolerance | Household device graph with explicit consent |
| Legitimate SIM replacement resembles SIM swap | Verified-change mitigation; SIM novelty alone does not trigger a security floor | Signed SIM-change assurance from the bank/telco workflow |
| Attacker forges telco lifecycle fields | All lifecycle fields are ignored unless the trusted gateway attests the envelope | Mutual TLS plus signed gateway claims and key rotation in production |
| Raw subscriber identifiers leak | The API accepts change flags and bounded ages/counts, not raw IMSI/ICCID values | Retention limits and field-level access control |
| Missing USSD or feature-phone telemetry | Channel-aware evidence coverage and core-banking fallback | Gateway clock-quality monitoring and telecom assurance feeds |
| Behavioural telemetry becomes surveillance | Only bounded deviations and privacy-reduced signatures are required by the scorer | Consent, minimisation, retention limits, on-device aggregation, and DPIA |
| Model unavailable or incompatible | Failover to transparent rules-only mode | Signed registry, canary deployment, automatic rollback |
| Audit entries altered | SHA-256 chained audit entries | External anchoring and WORM retention |
| Entire database deleted | Not prevented by local chain | Cross-region backups and independent audit witness |
| Model extraction through API | Only risk result and bounded reasons returned | Rate limits, query monitoring, response coarsening |
| API misuse | API-key dependency and validation | mTLS, OAuth workload identity, scopes, WAF, rate limits |
| Permanent harm from false positive | Reversible actions and Regret Budget | Customer appeal, SLA, compensation and governance |
| Popular merchant mistaken for mule | Mule floor requires rapid cash-out, not fan-in alone | Merchant/entity allow-lists governed outside the client request |
| Coercion telemetry becomes surveillance | Ignored unless consented and device-attested; no audio or raw screen content | On-device inference, DPIA, opt-out, accessibility and abuse review |
| Recourse helps attacker tune evasion | Customer wording omits thresholds and exact feature cut-offs | Monitor repeated clearance attempts and rotate controls |
| Attacker declares a fake outage | Signed, fresh admin heartbeat with replay-resistant nonce | Independent health sources, mTLS and hardware-backed keys |
| Edge capsule is modified or rolled back | HMAC verification, model/policy binding and expiry | Signed transparency log and monotonic hardware counter |
| Outage queue is altered | Tenant-scoped hash chain; reconciliation blocks | Encrypted replicated log and independent witness |
| Core rail is unavailable | Transaction stays held; explicit no-settlement customer receipt | Ledger-owned authorization tokens and tested alternate site |
| Recovery storm overloads services | Bounded reconciliation batch and pending queue visibility | Rate-adaptive workers, circuit breakers and priority tiers |
| Client forges a trusted agent terminal | Unattested claims contribute zero terminal evidence; envelope is agent-channel-only | mTLS gateway identity, signed assertions and hardware-backed keys |
| Busy market agent is treated as a campaign | Cross-customer volume needs beneficiary concentration plus suspicious corroboration | Registered merchant context, cohort calibration and independent field validation |
| One wrong report quarantines an agent | One victim creates monitoring only; two need independent approval; three independent victims quarantine | Formal appeal, reinstatement SLA and case-quality weighting |
| Sketch token is guessed or linked across epochs | Seven-day keyed token, no token return and bounded retention | VOPRF/PSI, HSM rotation, query privacy and operator separation |
| Malicious bank poisons shared intelligence | Signed enrolled issuer, rate limit, evidence allow-list, expiry and independent-bank count | Federation governance, issuer trust scoring, case sampling and sanctions |
| Shared match blocks an innocent customer | Uncorroborated or single-bank evidence is monitoring-only; exchange contribution tops out at delay | Joint appeal SLA, field calibration and compensated-error governance |
| Fraud-sketch report is replayed or altered | Canonical HMAC signature, freshness, nonce and conflicting-ID rejection | mTLS, hardware-backed institution keys and transparency log |
| Consortium is unavailable during power/network cuts | Signed 24h cache, score/confidence discount and explicit source label | Replicated exchange, regional failover and shorter risk-calibrated capsules |

## Security invariants

- The current event is never part of its own behavioural history.
- Failed authentication and recovery requests do not establish a trusted device or SIM.
- A verified SIM change cannot activate the device-and-SIM critical security floor by itself.
- Missing optional handset telemetry is uncertainty, not evidence of guilt.
- A high-risk held event cannot immediately normalise its own behaviour.
- Model failure must not make the endpoint unavailable; transparent rules remain active.
- No decision is represented as proof that a person committed fraud.
- Every disruptive action has a defined expiry or human-review route.
- Recipient graph aggregates use only events strictly earlier than the current transaction.
- Coercion telemetry cannot affect risk unless consent and device attestation are present.
- Every interrupted decision returns at least one safe recourse route.
- Unavailable evidence never increases decision confidence.
- Outage activity never teaches the behavioural baseline.
- An isolated payment is never represented as settled.
- Reconciliation performs no automatic settlement and stops if journal integrity fails.
- Agent-terminal aggregates use only prior attested events, and missing terminal intelligence cannot lower risk.
- A single terminal report cannot quarantine an agent.
- A single institution's fraud sketch cannot trigger an intrusive customer action.
- Multiple shared sketches without local corroboration cannot exceed monitored approval.
- Cross-bank evidence alone cannot justify a hold, and every shared report expires or can be revoked.
- Raw sketch source values and institution identities are not stored in shared tables or returned by the API.

## Non-goals

- Password or PIN authentication itself.
- Device malware detection.
- Sanctions screening and AML case management.
- Final settlement execution.
- Definitive attribution of an attacker.
- Production-grade key management or high availability.
- Deep multi-hop fraud-ring community detection or definitive mule attribution.
