# AegisMesh Private Fraud-Sketch Exchange

## Purpose

AegisMesh lets participating financial institutions contribute compact, expiring fraud indicators
without sharing customer records or raw identifiers. It extends AegisTwin's original recipient-only
consortium control to three bounded indicator families:

- tokenised recipient or mule destinations;
- gateway-attested agent terminals; and
- categorical campaign-stage sketches such as recovery + SIM change + cash-out.

The exchange is decision support, not an accusation registry. Shared evidence never causes a
permanent block and cannot justify an intrusive action without corroborating evidence inside the
customer's own institution.

## Implemented v1.3 prototype

1. The reporting institution signs a report with its own enrolled HMAC key.
2. The service verifies issuer enrolment, signature, freshness, evidence class, nonce and rate limit.
3. The source value is normalised and transformed into an epoch-scoped HMAC token.
4. Storage keeps the rotating token, tokenised institution, coarse evidence class, confidence,
   timestamps, expiry and revocation state. It does not keep the source identifier.
5. One institution produces an `observe_only` score. Two independent institutions produce a
   `shared_watch`; three or more can produce `high_confidence` shared evidence.
6. The local AegisTwin decision combines the exchange result with sender, recipient, trajectory,
   channel, agent-terminal and model evidence.
7. An uncorroborated exchange match is capped at monitoring. A corroborated match can contribute
   up to a reversible delay. A hold still requires stronger local evidence.
8. Every report and revocation enters the tamper-evident audit chain.

## Shared and excluded fields

Shared storage contains only:

- indicator type;
- 256-bit rotating indicator token;
- 256-bit institution token;
- epoch identifier;
- bounded confidence and approved evidence class;
- observation, creation and expiry times;
- active/revoked state; and
- a digest of the authenticated report.

It excludes account numbers, recipient identifiers, names, BVNs, phone numbers, device IDs, SIM
identifiers, terminal identifiers, IP addresses, coordinates, transaction histories and behavioural
profiles. Local banking events remain inside the bank boundary.

## Scoring and customer-action ceiling

The aggregate uses independent-institution count, evidence quality, report confidence, freshness and
expiry. The exchange result is surfaced separately from fraud risk as `fraud_sketch_exchange`.

| Shared evidence | Local corroboration | Maximum exchange-driven treatment |
|---|---|---|
| One institution | Any | Allow with monitoring |
| Two or more | No | Allow with monitoring |
| Two or more | Yes | Reversible settlement delay |
| Any | Strong local critical evidence | Local policy may independently choose a hold |

This distinction prevents an incorrect or poisoned consortium report from silently becoming an
automatic customer block.

## Integrity, poisoning and correction controls

- Institution-specific signatures prevent one enrolled bank from merely claiming another issuer's
  identity in the prototype.
- An allow-list and per-institution hourly quota constrain Sybil and flooding behaviour.
- Single-use nonces reject replay.
- Report IDs are idempotent; conflicting reuse is rejected.
- Only approved high-quality evidence classes are accepted, at confidence 0.60 or higher.
- Reports expire within 30 days and decay with age.
- The original issuer can submit a separately signed revocation.
- Revocation immediately refreshes the cached aggregate and is audit recorded.
- API responses never return indicator or institution tokens.
- Tenant-local events and the cross-bank exchange are stored and reasoned about separately.

## Power and network outage behaviour

Each live aggregate produces a signed short-lived Fraud-Sketch Capsule. If the consortium dependency
is unavailable, AegisTwin may use a still-valid capsule with a 15% risk discount and 25% confidence
discount. The decision response labels the source `signed_cache`. An expired or invalid capsule is
ignored, and exchange unavailability lowers decision confidence rather than being interpreted as
proof of safety. Outage events remain subject to the existing no-false-settlement, learning-freeze and
reconciliation controls.

## API

- `POST /v1/fraud-sketch/reports` - analyst-only signed report ingestion.
- `POST /v1/fraud-sketch/reports/{report_id}/revoke` - issuer-signed correction.
- `GET /v1/fraud-sketch/status` - analyst-only privacy-reduced aggregate status.
- `POST /v1/consortium/reports` - deprecated compatibility endpoint for the original recipient-only
  demonstration.

See `docs/API_REFERENCE.md` for request examples and `scripts/demo_fraud_sketch_exchange.py` for an
end-to-end signed example.

## Honest privacy boundary and production roadmap

The v1.3 implementation is **privacy-reduced**, not a claim of cryptographic anonymity. A consortium
operator holding the prototype token key can test guesses from a small identifier space. Production
requires managed institutional identity, HSM-held and rotated keys, formal evidence/appeal rules,
separate operator duties, penetration testing and legal data-sharing governance.

A stronger deployment can replace the shared token service with a VOPRF or private-set-intersection
protocol. RFC 9497 specifies VOPRFs in which the server does not learn the client's input or output:
https://www.rfc-editor.org/rfc/rfc9497.html. NIST describes FHE, MPC, PSI and differential privacy as
privacy-enhancing approaches applicable to collaborative financial-fraud computation:
https://csrc.nist.gov/projects/pec/fhe.

## Reproducible evidence

Run:

```bash
python scripts/demo_fraud_sketch_exchange.py
pytest tests/test_fraud_sketch.py
```

`artifacts/fraud_sketch_exchange.json` records the chronological baseline, one- and two-institution
effects, local-corroboration ceiling, signed outage cache, legitimate-biller hard negative, signature
tampering rejection, raw-value storage check, revocation, ingestion latency and audit-chain result.
