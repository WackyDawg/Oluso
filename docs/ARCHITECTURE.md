# Architecture

## v1.3 OlusoMesh private fraud-sketch envelope

Enrolled institutions sign compact recipient, attested agent-terminal or categorical campaign reports. The exchange validates issuer, freshness, nonce, evidence quality and rate before replacing the source value with a seven-day epoch HMAC token. Shared storage contains rotating indicator/institution tokens, coarse evidence, confidence, expiry and revocation state - never customer records or source identifiers. One issuer is observe-only; two independent issuers still cannot interrupt a customer without local corroboration. Corroborated exchange evidence can contribute a reversible delay but not a hold. Each live aggregate creates a signed short-lived capsule; an outage cache is explicitly discounted and lowers decision confidence. See [Private Fraud-Sketch Exchange](PRIVATE_FRAUD_SKETCH_EXCHANGE.md).

## v1.2 agent-terminal integrity envelope

Agency events can carry an optional gateway-attested, privacy-reduced terminal envelope. Before customer scoring, the service builds causal cross-customer terminal aggregates and reads tenant-bound, decaying terminal reputation. The transparent scorer treats this as a parallel risk lens and applies a security floor only for a compound campaign or independently confirmed terminal harm. A busy terminal with broad customer traffic but no concentrated beneficiary, authentication failures, location mismatch or rapid recipient cash-out is not a campaign. Feedback updates require distinct victims and independent approval before escalation; unattested claims contribute no terminal evidence.

See [Agent-Terminal Integrity Twin](AGENT_TERMINAL_INTEGRITY.md).

## v1.1 resilience envelope

Signed infrastructure heartbeats drive `online`, `degraded`, `isolated` and `reconciling` modes. A tenant-scoped signed edge capsule binds the approved model hash/version and policy version. Degraded decisions retain the fraud score but reduce decision confidence, list unavailable evidence and apply a conservative safety envelope. Isolated monetary instructions are scored only as local advice, remain held and receive a customer-safe reference stating that no settlement occurred. Every outage decision enters a tamper-evident store-and-forward journal and is excluded from profile learning. Restored services must verify the journal and non-mutatingly re-score each pending event before the controller returns online; reconciliation never auto-settles.

The prototype uses HMAC and SQLite to make the controls executable on one laptop. Production requires mTLS workload identities, hardware-backed keys, an encrypted replicated log, durable orchestration, a concurrent ledger connector and independently tested business-continuity procedures. See [Power and Network Outage Resilience](OUTAGE_RESILIENCE.md).

## v1.0 platform envelope

The scoring path now sits inside a tenant and role boundary. Before scoring, attested evidence is freshness checked. After scoring, a Safe Learning Firewall assigns pending, trusted, excluded or revoked state; transaction lifecycle state and an outbox event are persisted; high-priority or sampled decisions enter the analyst queue; and event/feature/model/policy/cutoff digests form an exact replay envelope. Campaign memory stores only stage signatures and account membership within a tenant. Consortium matching stores HMAC tokens and requires two independent institutions.

SQLite, the in-memory rate limiter and local outbox are prototype adapters. The production interfaces are a transactional feature store, distributed per-account ordering, durable message bus, workload identity, managed HSM-backed keys and independently anchored audit heads.

## Attested telco assurance for feature phones

The optional telco envelope crosses a separate trust boundary from the customer event. A bank or
telco gateway reduces raw network records into bounded indicators; it signs or attests the response
and does not send raw IMSI or ICCID values. The runtime ignores the whole envelope when
`gateway_attested=false`. This supplies useful SIM-lifecycle evidence for USSD without pretending a
feature phone can provide keystroke or motion sensors.

```text
Telco gateway -> attested privacy-reduced envelope -> schema validation -> feature fusion
Customer/app -> transaction and behaviour event  --^ (cannot attest its own envelope)
```

## Design goals

1. Detect a change in the person controlling an account, not merely an unusual transaction.
2. Support smartphone applications, USSD, and agency banking without requiring biometric hardware.
3. Keep historical aggregates under server control.
4. Combine a population model with a personal behavioural baseline.
5. Make every intervention reversible and explainable.
6. Limit avoidable customer friction without disabling critical protection.
7. Detect recipient-side mule behaviour that is invisible in a sender-only profile.
8. Model risk as a trajectory and protect a genuine customer who may be under coercion.
9. Pair every intervention with actionable, non-gameable recourse.
10. Continue safely through partial outages and never misrepresent an isolated transaction as settled.
11. Detect one compromised agent terminal harming several customers without penalising legitimate high-throughput agents.
12. Detect cross-institution fraud campaigns without centralising customer or transaction histories.

## Eleven uncommon defensive layers

### OlusoMesh Private Fraud-Sketch Exchange

Rotating tokens allow independent institutions to match recipients, attested terminals and campaign-stage motifs without returning the underlying identifier. Institution-specific signatures, freshness, replay nonces, allow-listing, rate limits, evidence classes, expiry and revocation constrain poisoning. Shared evidence is a separate risk view with a monitoring-only ceiling until local account evidence corroborates it. The v1.3 prototype is privacy-reduced; production VOPRF/PSI, HSM keys and formal consortium governance remain explicit gates.

### Agent-Terminal Integrity Twin

Gateway-attested terminal context is aggregated causally across customers. Customer diversity, recipient concentration, first-time-recipient ratio, failed authentication, value velocity, registered-location and shift mismatch, terminal novelty and independently confirmed terminal reputation form a separate explainable risk lens. One confirmed victim creates monitoring, two create an elevated floor and three quarantine; every update is tenant-bound and audited. Missing or unattested terminal evidence is surfaced as uncertainty, not interpreted as safety.

### Recipient Mule Graph Twin

The live service builds causal cross-account aggregates strictly from events before the transaction:
unique senders in 24 hours, the share of first-time senders, one-hour inflow, one-hour outflow, and
rapid cash-out ratio. A narrow security floor requires the combination of sender diversity,
first-time senders, and rapid cash-out. High inflow alone does not activate the mule rule, which
protects airtime sellers and other popular merchants. The prototype uses a bounded seven-day SQL
view; production should use a streaming graph feature store.

### Decaying Account Risk Window

Failed authentication, account recovery, PIN reset, and attested unverified SIM identity changes
create precursor contributions with explicit exponential decay and expiry. The API returns the
current state (`clear`, `watch`, `elevated`, or `high`), score, remaining hours, and active precursors.
This is a practical time-to-event approximation for the prototype, not a fitted survival model.

### Coercion-in-the-loop safety

An app may submit privacy-reduced call overlap, screen-sharing, recipient replacement, confirmation
backtrack, edit, hesitation, and on-device coercion indicators. Every field is ignored unless the
envelope states that collection was consented and device-attested. Strong evidence on a new
recipient selects `private_safety_pause`: a 15-minute reversible pause whose wording asks the user
to end calls or screen sharing and confirm privately, without accusing them or alerting a caller.

### Counterfactual recourse

Interrupted responses include structured options such as confirmation from a registered device,
an official bank callback, or automatic expiry/review. Each option names a safe channel and expected
clearance time. Thresholds and exact feature cut-offs are deliberately omitted from customer recourse.

### Adaptive attacker red-team

`scripts/adaptive_attack_search.py` searches 2,688 valid raw transaction configurations rather than
editing derived features. Its objective is to maximize transferable value below the 0.48
confirmation threshold and then minimize behavioural changes. The discovered evasion, mitigation
scores, and residual risk are written to JSON and Markdown without retraining on the found example.

### Decision Confidence Envelope

Risk and certainty are returned separately. The confidence envelope measures profile maturity,
channel/recipient evidence coverage, and model-versus-rule agreement. Low confidence is visible to
the analyst and prevents an automatic hold unless independent critical evidence exists.

### Cross-Channel Transition Twin

The account history is treated as an ordered channel sequence. Novel transitions, a new-device
login or enrolment, rapid app-to-USSD hand-off, and device inconsistency combine into a single
cross-channel takeover reason. Each feature uses only prior events.

### Confirmed Recipient Reputation Loop

Confirmed analyst feedback updates a 90-day, decaying recipient record keyed by a tokenised
identifier. One victim creates monitoring only; at least two distinct victims are required for the
strong security floor. This makes feedback useful across accounts without allowing one mistaken
label to block every sender.

### Calendar Rhythm Twin

After at least three observed months, repeated day-of-month, recipient and amount patterns reduce
false positive pressure. The mitigation never suppresses independent SIM, device, recovery,
coercion, mule or confirmed-recipient evidence.

### Personalised Friction Optimizer

Within the permitted risk band, policy compares the expected fraud exposure and the expected
customer cost of each reversible action. Regret-budget pressure, USSD effort, recurring-payment
evidence and decision uncertainty change the friction cost. The chosen and alternative costs are
returned for audit.

## Components

### Event ingestion

FastAPI validates identifiers, timestamps, coordinates, values, channels, and event types. Every event has a globally unique `event_id`; replays receive a conflict response. The development API key is an integration placeholder, not a consumer credential.

Optional app telemetry includes typed-versus-pasted input, median keystroke interval, device-tilt variance, and a privacy-reduced navigation signature. USSD does not depend on these app signals: the gateway can supply menu timing and a menu-path signature while the core bank supplies amount, balance, recipient, time, authentication, and velocity context.

### Graceful Degradation Ladder

Every response identifies which evidence path was available:

1. `app_rich_behaviour` combines core banking, device, interaction, typing, handling, and navigation signals.
2. `ussd_gateway_behaviour` uses server-visible transaction context, SIM/network context, menu timing, and menu paths.
3. `agent_network_behaviour` uses transaction, terminal, agent-network, location, and workflow context.
4. `core_banking_fallback` uses amount, balance drain, recipient, time, velocity, authentication, and recovery signals when optional telemetry is absent.

Missing optional telemetry lowers evidence coverage and produces an uncertainty note; it is not itself treated as proof of fraud.

### Historical event store

SQLite stores event envelopes, decisions, profiles, analyst feedback, tokenised recipient reputation, and audit entries. It uses WAL mode, foreign keys, per-account and tenant/time indexes (the recipient-graph window scan on every score is indexed on `(tenant_id, occurred_at)`), and a small pool of reused connections (a scored event touches the store about forty times, so per-call connection setup was a third of request latency); reads are lock-free and only writes take the process lock. Model inference uses a verified fast path that walks the fitted trees directly and falls back to sklearn's `predict_proba` if it does not reproduce it to 1e-6 on a probe set at load time. Production should use an encrypted relational store plus a streaming feature platform.

### Behavioural twin

For each account, the profile builder maintains robust amount statistics, common hours, trusted recipients, devices, SIMs, channels, network prefixes, and interaction speed. Confidence rises logarithmically and reaches maturity after roughly 50 trusted transactions.

The twin also stores robust typing, phone-handling, input-method, and navigation summaries when the channel supplies them. Verified SIM replacements remain visible as changes but receive a strong mitigation, while unverified device-and-SIM co-change can still trigger a security floor.

Failed authentication, recovery events, and interrupted high-risk transactions do not enrol their devices or SIMs into the trusted baseline. All events remain visible for investigation.

### Feature engine

The feature engine reads events strictly earlier than the event being scored. It calculates personal deviation, novelty, velocity, recovery context, travel speed, and USSD/app rhythm. This avoids the common error of accepting caller-provided behavioural averages.

### Hybrid risk engine

The population model identifies combinations seen across simulated takeover scenarios. The transparent anomaly scorer supplies per-account deviation and human-readable contributions. Fusion changes its weighting during cold start and applies narrow, individually named security floors (`SECURITY_FLOOR_RULES` in `oluso/scoring.py`; each decision records which fired) to high-confidence combinations such as:

- New device + new SIM + balance drain.
- Recovery event + new recipient.
- Failed authentication burst + new device.
- Impossible travel + new device.
- Many first-time senders + rapid recipient cash-out.
- Decaying precursor risk + new recipient.
- Attested coercion signature + new recipient.
- Attested cross-customer terminal campaign + concentrated beneficiary or authentication failures.

### Reversible policy engine

| Score | Default response |
|---:|---|
| `< 0.30` | Allow |
| `0.30–0.48` | Allow with monitoring |
| `0.48–0.66` | Trusted-channel confirmation |
| `0.66–0.84` | Fifteen-minute reversible settlement delay |
| `≥ 0.84` | Two-hour reversible hold and analyst review |

Attested coercion evidence selects a private 15-minute safety pause independently of the ordinary
response label. Every non-allow response includes structured recourse.

The Regret Budget records intrusive interventions over 30 days. Repeated noncritical challenges are replaced with less disruptive controls. High risk and explicit critical combinations override the soft budget.

Every policy result includes one customer-facing explanation sentence assembled from the strongest observable reasons. Internal feature names and model probabilities remain in the analyst view rather than the customer message.

### Audit chain

Each account creation, risk decision, and analyst feedback record is canonicalised and chained with SHA-256:

```text
entry_hash = SHA256(sequence | timestamp | type | entity | payload | previous_hash)
```

The chain excludes raw transaction data by recording event and feature digests. `/v1/audit/verify` recomputes every link and reports the first invalid sequence.

The model endpoint also exposes the model-artifact hash, training-dataset hash, and feature-schema hash. These bind a decision to the exact development evidence used to produce the model. A production registry should sign the complete bundle; an independent transparency service or permissioned ledger may periodically anchor the approved hashes without publishing customer data.

## Scoring sequence

```text
1. Authenticate integration request.
2. Validate the event and reject duplicate IDs.
3. Load trusted events occurring before the current event.
4. Build the pre-event behavioural twin.
5. Calculate sender, recipient-graph/reputation, trajectory, calendar, and cross-channel features server-side.
6. Run transparent anomaly and population ML scorers.
7. Fuse scores, calculate a separate decision-confidence envelope, and apply documented security floors.
8. Select a reversible response using expected action costs and the Regret Budget.
9. Persist event and decision.
10. Update the profile only when the event is eligible.
11. Append a privacy-reduced audit-chain entry.
12. Return risk, decision confidence, recipient reputation, reasons, alternative action costs, model version, and audit hash.
13. Return the evidence tier, risk window, one customer-ready explanation, and safe recourse options.
```

## Scaling path

- API replicas behind an mTLS gateway.
- Kafka or Redpanda event stream.
- Redis/Feast online feature store.
- PostgreSQL for case, decision, and policy state.
- Object storage for signed model bundles.
- Model registry with approval gates and rollback.
- Separate policy-decision and analyst-console services.
- Independent audit-head anchoring service.
- Distributed per-account ordering to replace the MVP's striped in-process locks.
