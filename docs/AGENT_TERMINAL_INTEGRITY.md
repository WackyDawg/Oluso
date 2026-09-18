# Agent-Terminal Integrity Twin

## Purpose

Oluso v1.2 adds a second unit of analysis for agency banking: the gateway-attested agent terminal. A customer-only detector can miss one compromised terminal that causes small, plausible-looking losses across many unrelated customers. The integrity twin asks whether the shared endpoint is exhibiting a cross-customer campaign while the customer twin still asks whether each instruction fits its account.

This is a Track A account-takeover control, not a separate project. Its output is fused into the same decision, reversible response, recourse, audit trail and analyst queue.

## Trust boundary and minimisation

`agent_token` and `terminal_token` are opaque gateway identifiers and are HMAC-tokenised before reputation storage. Registered location, approved shift and terminal age are optional bounded attributes. The entire envelope is ignored unless `gateway_attested=true`, and the live resilience controller can mark `agent_integrity` unavailable. A production gateway must replace the prototype attestation flag with mTLS workload identity and a signed assertion.

No customer device can designate itself as a safe terminal. Raw agent identity documents, customer biometrics and precise movement trails are not required.

## Causal signals

All aggregates use only events strictly earlier than the transaction being scored:

| Signal | Window | Interpretation |
|---|---:|---|
| Distinct customer accounts | 1 hour | Detects one endpoint touching many unrelated victims |
| Recipient concentration | 24 hours | Detects many customers being directed to the same beneficiary |
| First-time recipient ratio | 24 hours | Separates established customer-agent activity from novel payees |
| Failed-authentication ratio | 1 hour | Identifies repeated access or social-engineering failures |
| Value velocity | 1 hour | Gives scale context without making high throughput suspicious by itself |
| Location/shift mismatch | Current event | Detects attested terminal use outside its registered operating context |
| Terminal novelty | Current event | Raises uncertainty for newly commissioned endpoints |
| Confirmed reputation | 60-day decay | Propagates verified fraud across affected customer accounts |

The compound `AGENT_TERMINAL_CAMPAIGN` reason requires cross-customer diversity, concentrated recipient flow and at least one suspicious corroborator such as rapid recipient cash-out, authentication failures, location mismatch or confirmed terminal fraud. Busy volume alone is insufficient.

## Feedback and quarantine governance

Confirmed analyst feedback may update terminal reputation only when the scored event carried an attested terminal envelope. One independent affected account creates monitoring at 0.35. Two affected accounts create elevated reputation at 0.75 and require an independent second approver. Three affected accounts quarantine the terminal at 1.0 pending human review. Reports decay and expire after 60 days, and every change enters the SHA-256 audit chain.

Quarantine is a bank-side risk state, not an accusation or physical enforcement action. Production deployment needs a documented appeal, terminal-owner notification, investigation and reinstatement process.

## Power and network outages

When terminal intelligence is unavailable, Oluso lists it as missing evidence and lowers decision confidence. It does not manufacture a zero risk contribution. In isolated mode, a monetary instruction is never represented as settled; it receives a no-settlement reference, enters the tamper-evident journal and is re-scored after trusted services recover. Outage activity cannot teach the trusted behavioural baseline.

## Reproducible proof

Run:

```bash
python scripts/demo_agent_terminal.py
pytest tests/test_agent_terminal.py -q
```

The live proof in `artifacts/agent_terminal_demo.json` records:

- A legitimate busy terminal allowed at risk 0.086 with no campaign reason.
- A compromised terminal delayed at risk 0.740 after cross-customer failures and recipient concentration.
- Reputation progression from monitoring to elevated to quarantined across three independent victims.
- A post-quarantine transaction delayed at risk 0.760.
- A forged unattested terminal claim ignored with zero agent-evidence coverage.
- A valid 54-entry audit chain.

The chronological held-out evaluation detects 9/9 `agent_social_engineering` attacks and interrupts 0/69 `busy_agent_merchant_payment` hard negatives at the customer-confirmation threshold. These are synthetic prototype results, not field accuracy.

## Production boundary

The laptop prototype uses SQLite causal queries. A bank-scale deployment needs a partitioned streaming feature store, terminal-registry integration, signed gateway assertions, encrypted identifiers, distributed event ordering, network-wide case governance, bias monitoring across urban/rural agent cohorts and independent red-team validation. The detector must remain decision support with reversible controls; it must not be used as proof of agent misconduct.
