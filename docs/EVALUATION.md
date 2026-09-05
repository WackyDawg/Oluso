# End-to-End Evaluation

## Release assurance, robustness and platform verification

The full automated suite (see `README.md` for the current test count and coverage gate) runs on every change. The executable outage drill moves through degraded, isolated, reconciling and online states; validates the signed edge capsule; freezes profile learning; detects deliberate journal tampering; and performs no duplicate lifecycle action or automatic settlement. The agent-terminal proof allows a busy legitimate endpoint, delays a compromised cross-customer campaign, quarantines after three independent victims and ignores a forged unattested claim. See `artifacts/outage_resilience.json` and `artifacts/agent_terminal_demo.json`. Signed private-exchange evidence, action ceilings, revocation and outage cache are separately recorded in `artifacts/fraud_sketch_exchange.json`.

Warm full-API and concurrent SQLite results are kept in `artifacts/latency.json` and `artifacts/concurrent_load.json`. These laptop measurements prove executable paths, not a bank availability or production-scale claim.

This report evaluates the exact live fusion and policy thresholds, not only the population model.
All results use held-out synthetic Nigerian sessions and demonstrate pipeline behaviour, not production accuracy.

- Generated: `2026-09-05T21:47:44.435347+00:00`
- Model: `rf-calibrated-longitudinal-ng-7.0`
- Test events: `5400`
- Takeover events: `44`
- Synthetic takeover prevalence: `0.815%`
- Model-only ROC-AUC / PR-AUC: `0.9729` / `0.9231`
- Fused ROC-AUC: `0.9611`
- Fused PR-AUC: `0.9216`
- Model Brier / expected calibration error: `0.0010` / `0.0005`

## Live policy operating points

| Response threshold | Recall | Precision | False-positive rate | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| Monitor or stronger | 93.18% | 85.42% | 0.13% | 41 | 7 | 3 |
| Customer confirmation or stronger | 90.91% | 95.24% | 0.04% | 40 | 2 | 4 |
| Settlement delay or hold | 90.91% | 95.24% | 0.04% | 40 | 2 | 4 |
| Two-hour hold and review | 79.55% | 97.22% | 0.02% | 35 | 1 | 9 |

## Uncertainty of the headline numbers

With only 44 held-out takeovers, point estimates are wide. Intervals are 95% stratified percentile bootstrap (2000 resamples, seed 2026); Wilson intervals for the binomial rates are shown alongside. Quote the interval, not the point.

| Response threshold | Recall [CI] | Recall (Wilson) | FPR [CI] | FPR (Wilson) | Precision [CI] |
|---|---:|---:|---:|---:|---:|
| Monitor or stronger | 93.18% [84.09%, 100.00%] | [81.77%, 97.65%] | 0.131% [0.037%, 0.243%] | [0.063%, 0.270%] | 85.42% [76.00%, 95.24%] |
| Customer confirmation or stronger | 90.91% [81.82%, 97.73%] | [78.84%, 96.41%] | 0.037% [0.000%, 0.093%] | [0.010%, 0.136%] | 95.24% [88.89%, 100.00%] |
| Settlement delay or hold | 90.91% [81.82%, 97.73%] | [78.84%, 96.41%] | 0.037% [0.000%, 0.093%] | [0.010%, 0.136%] | 95.24% [88.89%, 100.00%] |
| Two-hour hold and review | 79.55% [65.91%, 90.91%] | [65.50%, 88.85%] | 0.019% [0.000%, 0.056%] | [0.003%, 0.106%] | 97.22% [91.18%, 100.00%] |

- Fused ROC-AUC: `0.9611` [0.9135, 0.9999]
- Model-only ROC-AUC: `0.9729` [0.9287, 0.9999]

## Component ablation at the customer-confirmation threshold

The live score is `max(blend, security_floor)` where the blend mixes the calibrated population model with the transparent behavioural scorer. Each row scores the held-out set with one component alone so it is clear how much detection is learned versus rule-based.

| Component | Recall | Precision | FPR | TP | FP | ROC-AUC |
|---|---:|---:|---:|---:|---:|---:|
| `model_only` | 90.91% | 95.24% | 0.037% | 40 | 2 | 0.9729 |
| `anomaly_only` | 93.18% | 26.80% | 2.091% | 41 | 112 | 0.9607 |
| `blend_without_floors` | 90.91% | 95.24% | 0.037% | 40 | 2 | 0.9611 |
| `floors_only` | 72.73% | 100.00% | 0.000% | 32 | 0 | 0.8977 |
| `fused_live` | 90.91% | 95.24% | 0.037% | 40 | 2 | 0.9611 |

## Detection attribution

For every alert at the customer-confirmation threshold: did the model/anomaly blend reach the threshold on its own, or did a named security floor lift it there?

| Outcome | Blend alone | Floor required | Both | Total |
|---|---:|---:|---:|---:|
| True positives | 8 | 0 | 32 | 40 |
| False positives | 2 | 0 | 0 | 2 |

- Share of true positives that needed a floor: **0.00%**; caught by the blend alone: **20.00%**.
- Floors present among floor-level true positives: `RECIPIENT_SINGLE_REPORT` (23), `RECIPIENT_MULTI_ACCOUNT` (20), `DEVICE_SIM_COCHANGE` (15), `MULE_FAN_IN_CASHOUT` (10), `ATTESTED_SIM_IDENTITY_CHANGE` (7), `OTP_AFTER_SIM_CHANGE` (7), `RECOVERY_THEN_NEW_RECIPIENT` (7), `FAILED_AUTH_NEW_DEVICE` (6), `CROSS_CHANNEL_SEQUENCE` (5), `COERCION_DURING_CALL` (2).

## Rare-fraud prevalence stress test

Projection uses the customer-confirmation operating point while changing only prevalence.

| Assumed takeover prevalence | Projected precision | Alerts / 10,000 | False alerts / 10,000 |
|---:|---:|---:|---:|
| 0.100% | 70.93% | 12.82 | 3.73 |
| 0.500% | 92.45% | 49.17 | 3.71 |
| 1.000% | 96.10% | 94.60 | 3.69 |

## Customer-protection hard negatives

| Legitimate scenario | Events | Customer-confirmation rate |
|---|---:|---:|
| Busy Agent Merchant Payment | 60 | 0.00% |
| Community Collection Payment | 56 | 0.00% |
| Emergency Transfer | 62 | 3.23% |
| Legitimate Failed Login Retry | 46 | 0.00% |
| Legitimate New Phone | 53 | 0.00% |
| Legitimate Post Recovery | 54 | 0.00% |
| Legitimate Travel | 49 | 0.00% |
| Payday Spending | 60 | 0.00% |
| Popular Merchant Payment | 57 | 0.00% |
| Recurring Monthly Payment | 51 | 0.00% |
| Shared Family Phone | 67 | 0.00% |
| Verified Sim Replacement | 44 | 0.00% |

## Interpretation

The challenge threshold begins at customer confirmation (`0.48`). Lower-risk events may be monitored without interrupting the customer. Higher-risk events receive reversible delays or holds. Neither model-only nor fused ranking is perfect after removing post-label reputation and event-type shortcuts and adding groomed-recipient attacks plus legitimate behavioural lookalikes. The account-disjoint result, separability audit and evidence-coverage leakage audit are in `artifacts/robustness.json`.

The synthetic generator, the transparent scorer and the security floors were designed by the same team against the same threat model, so the evaluation measures agreement with that model rather than real-world fraud. The ablation and attribution tables above exist so a reader can see exactly how much of the result comes from learned behaviour versus encoded rules.
