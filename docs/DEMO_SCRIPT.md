# Five-Minute Demonstration

## Fast v1.4 proof commands

Run `python scripts/release_smoke_test.py .` first. It stages a clean source copy, promotes the
checked-in `.env.example` to `.env`, imports the application and requires `/health` to return 200.
Then run `python scripts/evaluate_robustness.py`; it rejects perfect synthetic ranking and reports a
zero-customer-overlap account split.

Run `python scripts/demo_fraud_sketch_exchange.py` first. It shows a baseline score of 0.084, one institution raising monitoring only, two institutions still capped at 0.420 without local corroboration, and the same shared evidence contributing a reversible delay when local account behaviour corroborates it. It also proves signed outage cache, a legitimate biller with zero exchange score, signature tamper rejection, no raw source value in shared rows, issuer revocation and a valid audit chain.

Run `python scripts/demo_v5_features.py`. Its JSON shows five live results: low risk with separately
low decision confidence; a new-device app login followed by a high-risk USSD transfer; analyst
confirmation on account A raising monitoring for account B's payment to the same recipient; a
three-cycle monthly payment receiving calendar mitigation; and the alternative action costs used by
the friction optimizer. The run ends by verifying the audit chain.

Run `python scripts/demo_agent_terminal.py` for the agency-channel proof. It shows a busy legitimate
terminal remaining usable, one compromised endpoint linking several customers to a concentrated
recipient, reputation rising across three independent victims, terminal quarantine, a forged
unattested claim being ignored and a valid audit chain.

## 1. Start the system

```bash
docker compose up --build
```

Open `http://localhost:8501`.

## 2. Establish the legitimate behavioural twin

1. Select **Create demo account**.
2. Select **Seed normal history**.
3. Refresh the profile.
4. Explain that the server—not the phone—calculated the typical amount, recipients, device, SIM, channels, hours, location, and USSD rhythm.
5. Point out that the profile and all examples use Nigerian locations, NGN context, app, USSD, and agency channels.

## 3. Demonstrate a hard negative

Select **Legitimate new phone** and score it. The device is new, but the usual SIM, recipient, amount, balance, location, and rhythm remain consistent. The system should allow or monitor rather than freeze the customer.

Then select **Verified SIM replacement**. A new SIM is visible, but the verified-change signal suppresses the SIM-swap security floor. This directly demonstrates that changing a SIM is not treated as fraud.

## 4. Demonstrate takeover

Select **SIM-swap balance drain** and score it. Highlight:

- New device and SIM appearing together.
- New recipient.
- Amount far above the personal median.
- Most of the available balance being moved.
- Network and location change.
- Abnormal USSD speed.
- Population-model match.

The response is a reversible hold, trusted-channel confirmation, and analyst review—not an irreversible account closure.

## 5. Show accountable AI

Expand the policy and technical detail. Point out:

- Personal anomaly score.
- Population-model probability.
- Fused score.
- Profile confidence.
- Model version.
- Feature snapshot.
- Human-readable reasons.
- One customer-ready explanation sentence.
- Evidence mode, coverage, and missing optional signals.
- Audit hash.
- Decaying account-risk window.
- Safe recourse options and expected clearance time.

Select **Pasted-credential takeover** to show app-only signals: pasted input, typing-cadence change, unusual phone handling, an unfamiliar navigation path, a new device, and a new recipient. Contrast it with the USSD scenario, which remains useful without smartphone sensors.

Then select **Coercion-assisted transfer**. The genuine customer's familiar device and SIM remain in
use, but consented, device-attested call/screen-share and confirmation-friction signals select a
private 15-minute safety pause. Show the safe clearance routes and explain that raw call audio or
screen content is never collected.

Select **Compromised agent terminal**. The dashboard creates earlier attested activity from several
synthetic customers at one terminal, including failed authentication and concentrated transfers. The
trigger transaction should receive a reversible delay with `AGENT_TERMINAL_CAMPAIGN`. Contrast this
with `artifacts/agent_terminal_demo.json`, where an equally busy legitimate market terminal remains
at 0.086 risk because volume alone is not treated as wrongdoing.

## 6. Show the adaptive attacker and recipient graph

Open `docs/ADAPTIVE_REDTEAM.md` or run:

```bash
python scripts/adaptive_attack_search.py
```

The search tests 2,688 valid raw events. It finds an NGN 48,000 same-device, same-SIM, same-IP,
same-pattern evasion at score 0.293. Recipient mule context raises the identical event to 0.760 and a
reversible delay; adding a recovery precursor raises it to 0.780. State the residual risk plainly: a
fresh mule with no observed history can still evade the graph.

## 7. Demonstrate tamper detection

Select **Verify audit chain**. Explain that risk decisions and analyst feedback are SHA-256 chained. A production deployment could periodically anchor the chain head with an independent institution without putting customer data on a blockchain.

## 8. Closing statement

> AegisTwin asks six questions: does the customer still behave normally, does the recipient look like a mule, is the account entering a risk window, is the genuine customer being coerced, is the shared agent terminal harming several customers, and have independent banks privately observed the same fraud pattern? It answers with explainable AI, privacy-reduced collaboration, reversible intervention and actionable recourse across app, USSD, feature-phone and agency banking.
