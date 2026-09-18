# Model and policy governance

The deployed bundle exposes its model version and SHA-256 hashes of the serialized artifact, exact training data and ordered feature schema. The policy version and causal event cutoff are stored with every decision. Exact replay recomputes the provenance digest without querying newer evidence.

Release evaluation has two anti-shortcut gates. The chronological test fails if model-only ROC-AUC is perfect or if any individual feature reaches 0.98 separation AUC. A second account-disjoint experiment trains on 450 accounts and tests on 150 entirely unseen accounts. The present zero-overlap result is 83.33% confirmation recall and 0.1007% FPR, materially weaker than the normal chronological twin evaluation and therefore a useful generalisation warning.

OlusoMesh fraud sketches are post-model policy evidence and are not added to the trained feature schema. This prevents a delayed cross-bank label from leaking into model training or historical evaluation. Every decision records the applied exchange summary and its digest; live/cached source, independent-institution count, local corroboration and action ceiling remain inspectable. Production calibration must replay sketches chronologically using only reports available before each event.

## Fusion constants and security floors

Every number in score fusion is a governance constant, not a learned parameter, and lives in one place: `oluso.scoring` defines the model/anomaly blend weights (`0.68` when the profile is immature, `0.58` otherwise) and a table of fifteen named `SecurityFloorRule`s (for example `OTP_AFTER_SIM_CHANGE`, `RECOVERY_THEN_NEW_RECIPIENT`, `MULE_FAN_IN_CASHOUT`), while `oluso.policy.POLICY_THRESHOLDS` holds the response ladder (`0.30 / 0.48 / 0.66 / 0.84`). They were chosen on the synthetic validation split by inspection, which is disclosed rather than dressed up; field calibration must re-derive them from consented production data through the champion/challenger path. Each decision records which floors fired (`SECURITY_FLOOR_APPLIED` reason, `fusion_*` feature-snapshot fields) so an analyst can see whether the model or a rule produced the score.

## Uncertainty, ablation and attribution

Because the held-out set has only 44 takeovers, `artifacts/evaluation.json` reports 95% stratified bootstrap intervals and Wilson intervals for every operating point, a component ablation (model only, anomaly only, blend without floors, floors only, live fusion) and a detection attribution table stating how many true and false positives needed a floor. On the current corpus no true positive depended on a floor and the model alone matches the fused operating point; the floors therefore guarantee severity for known attack signatures rather than supplying recall. Publish the interval, not the point.

## Evidence-coverage leakage gate

`scripts/evaluate_robustness.py` audits every coverage/confidence feature (which telemetry was present) for label separation and fails the release if any exceeds 0.75 separation AUC. The worst on the current corpus is 0.596. This guards against a generator, or a real feed, that reveals labels through missingness.

## Drift and retraining

`GET /v1/governance/drift` compares a reference window (the earliest decisions, or the earliest since the last model promotion because every decision stores its `model_version`) with the most recent window of the same size, capped at 500 events each, after a minimum of 20 decisions. It reports PSI on the fused score, PSI on nine monitored features (the strongest behavioural signals plus the evidence-availability features so feed changes are visible), the change in action mix, and a `retraining_recommended` flag with reasons. PSI below 0.10 is stable, 0.10–0.25 is watch, and 0.25 or more is alert. The flag recommends; it never retrains or promotes, which remains a governed human action with a dataset, champion/challenger evaluation, threshold re-derivation, rollback owner and signed approval.

Policy simulation reports projected actions for proposed thresholds and explicitly marks that live policy was not changed. Any production threshold promotion should require a documented dataset, champion/challenger evaluation, false-positive budgets by channel and customer context, analyst capacity review, rollback owner and signed approval.

The equity endpoint intentionally does not infer ethnicity, gender, disability or other protected attributes. It reports intervention distribution and states the missing evidence. Proper outcome-parity testing requires representative labels, approved attribute governance and independent review.

Known model limitation: the constrained adaptive attacker can move NGN 48,000 from a trusted device using normal interaction behaviour below the intervention threshold. Recipient/campaign/precursor intelligence can mitigate such cases when present, but cannot guarantee detection in their absence. At the final confirmation threshold, all three held-out low-and-slow attacks and one of four remote-control USSD attacks are missed.
