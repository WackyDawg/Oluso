# Adaptive Attacker Red-Team

The harness searches valid raw transaction configurations rather than impossible feature vectors.
It is evaluation-only and does not retrain the model on the discovered evasion.

- Search space: `2688` valid candidates
- Model: `rf-calibrated-longitudinal-ng-7.0`
- Below-threshold evasion found: `True`
- Obvious attack score: `0.959`
- Best evasion amount: `NGN 48,000`
- Best evasion score before graph context: `0.293`
- Score with recipient graph context: `0.760`
- Score with graph plus precursor risk window: `0.780`

## Residual risk

A patient attacker using a fresh, previously unobserved recipient can still evade graph evidence; shadow-mode feedback and repeated adaptive search remain necessary.
