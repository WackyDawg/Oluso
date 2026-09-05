# AegisTwin v0.5 Intelligence Layers

This document defines the five v0.5 additions, their trust boundaries, decision behaviour, failure modes, and live proof. Risk is the estimated likelihood of fraud. Decision confidence is the support behind that estimate. They are deliberately different outputs.

## 1. Decision Confidence Envelope

`decision_confidence.score` combines profile maturity (40%), channel evidence coverage (35%), and agreement between the calibrated population model and transparent anomaly scorer (25%). Recipient intelligence coverage is included when a recipient is present. The response also exposes a level, the three components, and plain reasons.

- Low risk + high confidence means the event is both ordinary and well observed.
- Low risk + low confidence means “no strong danger observed, but the baseline is thin”; AegisTwin allows with monitoring and says what evidence is missing.
- High risk + low confidence cannot cause an automatic hold unless independent critical evidence exists. The policy downgrades it to a reversible delay.
- Model failure does not become false certainty: scorer agreement defaults to an explicitly uncertain value and the reason says the model was unavailable.

This is not a calibrated probability that the decision is correct. Production should calibrate confidence against abstention accuracy, missingness, drift and out-of-distribution cohorts.

## 2. Cross-Channel Transition Twin

The feature engine orders earlier events and derives transition novelty, different-channel events in 15 minutes, new-channel/new-device authentication in 24 hours, app-to-USSD hand-off, and cross-channel device mismatch. A compound takeover reason requires a new enrolment plus a rare transition plus a hand-off or device mismatch. The engine reads only events earlier than the scored transaction.

The synthetic `cross_channel_takeover` family creates a new-device app login eight minutes before a USSD transfer. In the held-out window, all 4 generated cases reached customer confirmation or stronger. This sample is too small for a field claim; it proves the sequence is represented and executable.

## 3. Confirmed Recipient Reputation Loop

Only analyst feedback labelled `account_takeover` or `other_fraud` updates recipient reputation. Recipient identifiers are SHA-256 tokenised before shared storage. Each record stores report count, distinct reporting accounts, first/last confirmation, status and a 90-day expiry.

- One distinct victim: score 0.35, decays over 90 days, and creates a 0.42 monitoring floor. It cannot interrupt a customer by itself.
- Two distinct victims: score 0.75 and a 0.76 reversible security floor.
- Three or more: score 1.0 and `high` reputation status.
- Repeated reports from the same account do not increase the independent-victim count.

The live proof confirms fraud on account A, then scores account B paying the same recipient: risk rises from the source case's 0.098 to 0.420 and account B is allowed with monitoring. This demonstrates propagation without turning one possibly mistaken report into a block.

Production requires appeals, analyst RBAC, case-quality thresholds, consortium governance, collision-safe keyed tokens, and deletion/correction workflows. Plain SHA-256 is a prototype token, not a defence against guessing a small identifier space.

## 4. Calendar Rhythm Twin

Calendar confidence rises with distinct months of trusted history. After three earlier months, the engine recognises the same recipient within three days of the usual day and an amount within 20%. A strong recurring match reduces amount, time and recipient-novelty contributions rather than blindly approving the transfer. The payment still remains subject to SIM, device, recovery, coercion, mule and watchlist evidence.

The deterministic corpus contains 329 recurring-monthly-payment hard negatives. In the held-out set, 0 of 75 reached customer confirmation. The live proof produces `recurring_payment_match=1.0`, `calendar_confidence=1.0`, risk 0.074, and monitored approval.

## 5. Personalised Friction Optimizer

The policy estimates an NGN-equivalent expected cost for allow, monitor, confirmation, delay and hold. For each action it combines fraud probability × exposed amount × residual-loss factor with legitimate probability × customer-friction cost. Candidate actions are limited to the current risk band so an uncertain cost estimate cannot jump from low risk to a hold.

Friction cost rises when the account has reached its Regret Budget, when USSD makes confirmation harder, when a payment matches a mature monthly rhythm, or when decision confidence is low. Coercion and independently critical evidence remain protected overrides. The API returns every action cost, the selected cost and the personalisation reasons so analysts can audit the choice.

The cost numbers are policy utilities, not literal fees or a claim about an individual customer's income. A bank must set them through customer research, loss data, emergency-payment policy, fairness testing and governance.

## Reproduce the live proof

```bash
python scripts/demo_v5_features.py
```

Machine-readable output is written to `artifacts/v5_feature_demo.json`. The run also verifies the audit chain.
