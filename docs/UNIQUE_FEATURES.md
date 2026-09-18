# Oluso v1.4 - Customer, recipient, terminal and private consortium integrity

## Platform differentiators

Oluso now demonstrates an attack-and-decision lifecycle, not only a classifier: quarantined learning can be reversed, multi-account campaign mechanics can propagate without sharing raw identities, independent banks can contribute HMAC-tokenised recipient intelligence, decisions can be replayed against the exact causal cutoff, and settlement can be cancelled through an idempotent audited state transition. Judges can also inspect the policy what-if result, drift sample gate, equity limitation, analyst queue, privacy workflow, SBOM, load test and restore proof.

The v1.1 outage layer adds a signed four-state controller, expiring edge decision capsule, missing-evidence confidence envelope, customer-safe no-settlement receipt, tamper-evident offline journal and exactly-once reconciliation drill. This answers the challenge's Nigerian power/network-cut condition with executable evidence rather than a roadmap claim.

The v1.2 Agent-Terminal Integrity Twin adds a third accountable unit of analysis. It recognises one compromised agency endpoint affecting several customers, requires suspicious corroboration before applying a campaign floor, propagates confirmed terminal harm across distinct victims, and protects ordinary high-throughput market agents with a dedicated hard-negative cohort.

The v1.3 OlusoMesh layer adds a privacy-reduced cross-institution unit of analysis. Banks contribute signed, rotating recipient, attested-terminal or campaign sketches without centralising customer histories. One issuer is observe-only; even two issuers remain monitoring-only until local behaviour corroborates the pattern. Signed cache, correction and explicit VOPRF/PSI production gates keep the privacy and availability claims bounded.

The v1.4 release-assurance layer removes post-label reputation and event-type shortcuts from model
training, adds groomed-recipient attacks and legitimate precursor lookalikes, rejects perfect ranking,
measures unseen accounts, and boots the packaged source against its own environment template before
release. It makes weak results visible instead of optimizing the submission around a perfect score.

## Ten fraud-intelligence features

The original five layers below remain implemented. Five additional runtime layers are documented
in [V5 Intelligence Layers](V5_INTELLIGENCE_LAYERS.md): Decision Confidence Envelope,
Cross-Channel Transition Twin, Confirmed Recipient Reputation Loop, Calendar Rhythm Twin, and
Personalised Friction Optimizer.

## 1. Recipient Mule Graph Twin

Sender-only behavioural systems miss a recipient collecting from many victims. Oluso therefore
maintains a second unit of analysis: causal recipient aggregates across accounts. The current
prototype calculates unique senders in 24 hours, first-time-sender ratio, one-hour inflow/outflow,
and rapid cash-out ratio. The security floor requires diverse first-time senders **and** cash-out;
fan-in alone is deliberately insufficient. This is verified with a popular-airtime-merchant hard
negative and automated regression tests.

Production evolution: stream signed transaction events into a bounded graph feature store; add
cash-out endpoint risk, weakly connected components, time-respecting paths, and analyst-confirmed
mule labels. Do not publish raw graph neighbourhoods to customers.

## 2. Adaptive Attacker Harness

The red-team harness searches 2,688 valid event configurations, varying amount, channel, device,
SIM, IP, input behaviour, navigation, timing, and interaction speed. It found an NGN 48,000
same-device/same-SIM evasion scoring 0.293—below customer confirmation. Recipient graph context
raised the identical transaction to 0.760; graph plus a recovery precursor raised it to 0.780.

This is intentionally an evaluation artifact, not self-training. The residual risk is explicit: a
patient attacker using a fresh recipient with no precursor history can still evade these layers.

## 3. Coercion-in-the-loop Protection

Account takeover assumes the criminal replaces the customer. Coercion fraud keeps the genuine
customer present and directs them. Oluso can consume privacy-reduced call overlap, screen share,
recipient replacement, confirmation backtrack, amount edit, hesitation, paste-during-call, and an
on-device safety score. These values are zeroed unless collection is consented and device-attested.

Strong evidence on a new recipient selects `private_safety_pause`: a reversible 15-minute pause with
wording that asks the customer to end the call or screen share and confirm privately. It does not
accuse the customer and avoids displaying a message that would teach the caller how detection works.

## 4. Decaying Account Risk Window

Rather than judging each payment in isolation, Oluso tracks whether an account is entering a
risk period. Failed authentication, recovery, PIN reset, and attested unverified SIM identity changes
contribute time-decaying hazard. Each precursor expires after a bounded window. The API exposes the
state, score, remaining hours, and precursor categories for analysts and policy, not raw secrets.

The MVP uses transparent exponential decay. A production pilot could compare this with calibrated
survival or point-process models after delayed labels and censoring are handled correctly.

## 5. Counterfactual Actionable Recourse

An explanation says why; recourse says what safely happens next. Every interrupted decision returns
structured options with action, description, estimated clearance, and safe channel. Examples include
registered-device confirmation, an official bank callback, and automatic expiry or review.

Recourse deliberately avoids exact thresholds and feature cut-offs. This makes the system more useful
to customers without turning the explanation endpoint into an attacker-tuning oracle.

## Evidence checklist

- `tests/test_network.py`: mule versus popular-merchant distinction and tracker parity.
- `tests/test_features.py`: risk decay and consent/attestation enforcement.
- `tests/test_policy.py`: private safety pause.
- `tests/test_service.py`: persisted recourse and live coercion decision.
- `artifacts/evaluation.json`: chronological held-out performance and cohort results.
- `artifacts/adaptive_redteam.json`: discovered evasion, mitigations, and residual risk.
- `artifacts/latency.json`: complete request-path latency under one second on the test laptop.
- `artifacts/outage_resilience.json`: outage state, capsule, tamper, reconciliation and recovery-objective evidence.
- `tests/test_resilience.py`: signed heartbeats, learning freeze, safety envelope, journal integrity, recovery idempotency and RBAC.
- `tests/test_agent_terminal.py`: busy-agent safeguard, attestation boundary, cross-customer campaign, analyst-only status and three-victim quarantine.
- `artifacts/agent_terminal_demo.json`: actual service-run proof for legitimate, compromised, quarantined and forged terminal cases.
- `tests/test_fraud_sketch.py`: issuer signatures, nonces, private storage, institution independence, action ceilings, outage cache, revocation and indicator types.
- `artifacts/fraud_sketch_exchange.json`: actual cross-bank baseline, propagation, local corroboration, biller hard negative, tamper, revocation and cache proof.
- `artifacts/robustness.json`: separation audit and zero-overlap account evaluation.
- `tests/test_config.py` and `scripts/release_smoke_test.py`: source-template parsing and packaged startup proof.
