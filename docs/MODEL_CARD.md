# Model Card: AegisTwin Population ATO Model

Version: `rf-calibrated-longitudinal-ng-7.0`. The population model retains the customer,
recipient, cross-channel, calendar, risk-window, coercion and agent-channel signals, but version 7
removes post-label recipient-reputation fields and event-type shortcut flags from model training.
Those signals remain available to the transparent policy layer where their timing and effect are auditable.

## Intended use

The model estimates how closely an event's server-derived features resemble simulated account-takeover scenarios. It is one input to a hybrid risk decision and must not be used alone to accuse, punish, or permanently deny service.

## Model

- Calibrated Random Forest classifier.
- 160 trees per base estimator.
- Balanced subsampling.
- Sigmoid probability calibration with three folds.
- Chronological 65% train, 17% validation, and 18% test division.
- A model-only diagnostic threshold selected on validation data at a target false-positive rate no greater than 0.5%.
- Production-style reporting at the actual fused policy thresholds (`0.30`, `0.48`, `0.66`, and `0.84`).

## Development dataset

Thirty thousand chronological transactions are generated for 750 Nigerian account personas. The generator first emits raw accounts, sessions, authentication events, transactions, recipient-network events, shared agent terminals, delayed confirmations, calendar cycles, and attack precursors. The production `FeatureEngine` then derives training rows from earlier trusted history. Overall takeover prevalence is about 0.81%; the held-out segment contains 44 takeovers among 5,400 events.

Attack families include SIM-swap drain, credential stuffing, recovery abuse, remote-control USSD activity, low-and-slow takeover, agency-channel social engineering, coercion-assisted transfer, and cross-channel takeover. Legitimate hard negatives also include popular-merchant fan-in without rapid cash-out and recurring monthly payments.

Signal distributions overlap deliberately. Groomed-recipient attacks reuse familiar infrastructure, while legitimate recovery, failed-login retry and cooperative-collection cases mimic suspicious precursors. A release gate rejects perfect model ranking or a single feature with separation AUC of 0.98 or greater. The generator is reproducible through `scripts/generate_synthetic.py`.

## Held-out end-to-end synthetic metrics

| Live response threshold | Recall | Precision | False-positive rate |
|---|---:|---:|---:|
| Monitor or stronger | 93.18% | 85.42% | 0.1307% |
| Customer confirmation or stronger | 90.91% | 95.24% | 0.0373% |
| Settlement delay or hold | 90.91% | 95.24% | 0.0373% |
| Two-hour hold and review | 79.55% | 97.22% | 0.0187% |

Model-only ROC-AUC/PR-AUC are `0.9729`/`0.9231`; fused ROC-AUC/PR-AUC are `0.9611`/`0.9216`. At the customer-confirmation threshold the system detected 40 of 44 simulated takeovers (95% bootstrap interval 81.8%–97.7%) with two false confirmations among 5,356 normal events (FPR 0.037%, interval 0.000%–0.093%). The calibrated model alone reaches the same operating point; the security floors alone reach 32 of 44 with no false alerts. The best single feature has separation AUC `0.9385`, below the release ceiling. In a separate account-disjoint test with zero customer overlap, confirmation recall is 83.33% with 0.1007% FPR. These are synthetic engineering tests, not real-bank performance.

See [End-to-End Evaluation](EVALUATION.md) for rare-prevalence projections, channel cohorts, attack-family recall, and hard-negative intervention rates.

These results validate code and scenario separability only. Synthetic data cannot reproduce customer diversity, network outages, handset sharing, fraud adaptation, label delay, or investigator bias.

## Runtime fusion

The model probability is blended with a personal anomaly score. During cold start the population model receives more weight; when personal history matures, the transparent personal scorer receives more weight. Fifteen named security floors (`aegistwin.scoring.SECURITY_FLOOR_RULES`) cover high-concern combinations and are recorded per decision so rule-driven scores are distinguishable from model-driven ones. A separate confidence envelope reports profile maturity, data coverage and scorer agreement; it is not the risk probability.

## Required validation before production

- Representative, consented, de-identified event data.
- Temporal out-of-sample and cross-region testing.
- Separate app, USSD, agent, feature-phone, and shared-device cohorts.
- Precision/recall and customer-friction analysis by relevant demographic groups.
- Recall at fixed operational false-positive budgets.
- Calibration plots and expected calibration error.
- Fraud-loss and intervention-cost simulation.
- Red-team replay of adaptive low-and-slow attacks.
- Shadow deployment before any customer-facing action.
- Independent threshold and feature-governance approval.

## Known limitations

- Raw events are synthetic and still simplify real telecom outages, noisy gateway clocks, customer accessibility needs, and adversarial adaptation.
- No concept-drift monitor is implemented in the MVP.
- Random Forest explanations use the transparent companion scorer, not exact SHAP contributions.
- Location can be missing or inaccurate.
- Shared-device configuration is account-level rather than household-graph based.
- The recipient graph is shallow and aggregate-based, not a production fraud-ring graph.
- Recipient reputation depends on analyst labels that can be delayed, wrong or biased; production needs appeal and governance controls.
- Agent-terminal evidence is a transparent companion lens, not learned inside the Random Forest; its thresholds require field calibration and rural/urban agent-cohort review.
- Adaptive search found a same-device, same-SIM, same-pattern NGN 48,000 evasion at score 0.293 when recipient history and precursors were absent.
- The current held-out sample misses all three low-and-slow attacks and one of four remote-control USSD attacks at the customer-confirmation threshold; these small cohorts are disclosed, not generalized.
- Model artifact loading uses `joblib`; only signed internally produced artifacts should be loaded.
