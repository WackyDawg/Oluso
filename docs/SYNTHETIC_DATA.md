# Synthetic Data Methodology

## Final corpus

The final deterministic build uses seed `2026`, 30,000 scored sessions across 750 synthetic
accounts, a requested 1% attack-injection probability after profile maturity, and a 12% hard-negative
probability. Because attacks are injected only after eight historical events, the realized full-corpus
takeover rate is about 0.81% (244 takeovers). The time-held-out test window contains 5,400 sessions and
44 takeovers (0.81%). No real customer, bank, telco, agent, or location trace is used.

For USSD and selected app sessions, the generator may add a privacy-reduced, gateway-attested telco
envelope. Normal histories use old SIMs with stable identities. `sim_swap_drain` events use recent
activation, subscriber/card identity changes, repeat-swap counts, OTP proximity, and geographic
conflict. `verified_sim_replacement` creates the same scary change pattern but marks the replacement
as verified, making it a hard legitimate case. The external comparison dataset was not imported.

The generator also creates shared mule hubs. Before selected attacks, six synthetic feeder accounts
pay the same mule and that mule moves most of the funds to a cash-out endpoint. Separate
`popular_merchant_payment` hard negatives create many legitimate first-time senders without rapid
cash-out. This tests the false-positive failure a naive “many senders = fraud” rule would create.

`coercion_assisted_transfer` keeps the genuine customer's familiar device and SIM but adds a new
recipient plus consented, attested in-call/screen-share and confirmation-friction telemetry. Benign app
sessions sometimes carry low-valued attested telemetry, so envelope presence is not a label shortcut.

`cross_channel_takeover` can create a new-device app login before a USSD transfer. The
feature row is calculated only after the login has entered the prior history. Confirmed-recipient
features are also chronological: selected shared-mule cases schedule an analyst confirmation
two to fourteen days later. Only confirmations whose delay has elapsed may affect a later payment
to the shared mule hub, so the label of the current event is never used as its own feature.

Version 7 adds behavioural overlap intentionally. Some takeovers reuse previously seen or groomed
recipients, normal devices and plausible timing. Legitimate post-recovery payments, failed-login
retries and community cooperative collections produce precursor and network shapes that resemble
attacks. Population-model training excludes delayed confirmed-recipient reputation plus the direct
`is_transfer` and `is_withdrawal` flags; the policy may still use reputation as explicit post-model evidence.

`recurring_monthly_payment` creates three earlier payments roughly 92, 61 and 31 days before the
current event with the same synthetic landlord and amount. This hard negative exercises the
three-cycle calendar mitigation. The main per-persona timeline spans up to roughly 160 days.

Shared agent terminals are generated independently of customer accounts. `agent_social_engineering`
creates one attested compromised endpoint that touches several customers, concentrates transfers on
a common recipient and may show failed authentication, location or workflow anomalies.
`busy_agent_merchant_payment` creates legitimate high-throughput terminals serving many unrelated
customers and a registered market merchant without the suspicious corroborators. The incremental
`AgentTerminalTracker` calculates every row using only earlier events, so current labels cannot leak
into terminal features.

## Purpose

The dataset exists to demonstrate a reproducible account-takeover pipeline without exposing real customer data. It must not be presented as a substitute for consented bank or telecom validation data.

## Generated files

| File | Grain | Purpose |
|---|---|---|
| `data/synthetic_accounts.csv` | One row per account persona | Stable Nigerian location, normal channel, transaction range, interaction rhythm, trusted devices/SIMs, recipients, and shared-phone policy |
| `data/synthetic_events.csv` | One row per raw session event | Chronological authentication, recovery, app, USSD, agent, and transaction activity; includes session IDs and attack precursors |
| `data/training_features.csv` | One row per scored transaction | Features derived from earlier raw events by the same `FeatureEngine` used by the API |

Identifiers are artificial. Amounts are synthetic NGN values. Locations cover Lagos, Abuja, Kano, Port Harcourt, Ibadan, and Enugu.

## Generation sequence

1. A seeded NumPy generator creates 750 account personas.
2. Each persona receives a home region, primary channel, typical transaction amount and hour, trusted recipients, device/SIM identities, USSD/app timing, and optional shared-phone status.
3. Thirty thousand transactions are created chronologically. Each transaction has an account ID, session ID, event ID, timestamp, channel, amount, balance, recipient, and whatever telemetry that channel can realistically expose.
4. Mature accounts may receive one of eight takeovers or 12 legitimate hard-negative scenarios. The final overall takeover prevalence is about 0.81% after the eight-event warm-up period.
5. Credential-stuffing, recovery-abuse, remote-control, cross-channel, mule and monthly-payment scenarios create raw precursor events before the scored transaction. This allows the corresponding features to be calculated rather than injected.
6. The runtime `FeatureEngine` sees only events earlier than the candidate transaction and calculates the training row.
7. Takeover events are saved for investigation but marked profile-ineligible so they cannot teach themselves into the trusted baseline.
8. Output is globally sorted by time and split chronologically: 65% train, 17% validation, and 18% test.

## Attack families

- **SIM-swap drain:** unverified new SIM and device, new recipient, network/location shift, high balance drain, and abnormal USSD path.
- **Credential stuffing:** repeated failed sign-ins, a new device/network, pasted input, changed cadence/handling, and unfamiliar app navigation.
- **Recovery abuse:** account recovery followed by a new device, SIM, recipient, and unusually large transfer.
- **Remote-control USSD:** rapid menu navigation and a burst of probe transfers before payment to a new recipient.
- **Low and slow:** a modest amount, limited novelty, and intentionally overlapping normal behaviour.
- **Agency social engineering:** a gateway-attested shared terminal exhibits cross-customer diversity, concentrated recipient flow and authentication/location/workflow anomalies.
- **Coercion-assisted transfer:** familiar authenticated customer, new directed recipient, active call or screen share, recipient edits/backtracks, hesitation, and consented device-attested safety score.
- **Cross-channel takeover:** a new-device app authentication followed minutes later by an unusual USSD transfer and channel/device mismatch.

## Legitimate hard negatives

- Domestic travel.
- A legitimate new phone.
- A verified SIM replacement.
- Emergency hospital transfer.
- Payday spending.
- An explicitly shared family phone.
- A popular merchant receiving from many first-time customers without rapid cash-out.
- A recurring monthly payment to the same recipient, within three days and 20% of the established amount.
- A busy market agent serving many customers without concentrated suspicious flow or authentication failures.
- A legitimate payment soon after a genuine recovery event.
- A successful owner login and payment after mistyped credentials.
- A community or cooperative collection account receiving from many members without rapid cash-out.

These scenarios are essential: a detector that recognises attacks but challenges every new phone, emergency, or family handset does not solve the customer problem.

## Missingness and feature phones

USSD sessions deliberately omit smartphone-only signals. Device IDs are often absent, network prefixes and coarse location are intermittent, and typing/tilt signals are never required. Menu timing and navigation signatures represent data a cooperating USSD gateway could provide. When those are also absent, the runtime uses its core-banking fallback.

## Reproduction

```bash
python scripts/generate_synthetic.py \
  --rows 30000 \
  --seed 2026 \
  --fraud-rate 0.01 \
  --hard-negative-rate 0.12
python scripts/train_model.py
python scripts/evaluate_system.py
python scripts/evaluate_robustness.py
```

## Known simplifications

- Behaviour and attack distributions are designed rather than empirically estimated.
- A bank's true fraud prevalence may be below 0.1%.
- Network failures, gateway clock drift, accessibility tools, language differences, and customer migration are simplified.
- The generator models a lightweight many-sender/cash-out mule pattern but not deep collusion, laundering chains, community detection, or graph identity resolution.
- Analyst-confirmed recipient labels are delayed by two to fourteen synthetic days; real labels can arrive later, be wrong, be appealed, or never arrive.
- The adaptive search is bounded to the exposed event schema and is not a full reinforcement-learning attacker.
- Coercion telemetry is simulated and needs consent, accessibility, bias, and safety validation.
- Agent-terminal campaigns and busy-agent cohorts are designed; production needs registered-agent telemetry, rural/urban cohort analysis and formal appeal data.

The evaluation therefore includes rare-prevalence projections and clearly labels every reported metric as synthetic.
