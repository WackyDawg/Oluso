# Model artifacts

`ato_model.joblib` — `rf-calibrated-longitudinal-ng-7.0`, a sigmoid-calibrated Random Forest
(3 folds × 160 trees) trained by `scripts/train_model.py` on `data/training_features.csv`.

The artifact is a dictionary containing the model, the ordered feature schema, version string,
`training_data_sha256`, `feature_schema_sha256`, the validation-selected diagnostic threshold and
training metrics. `aegistwin.scoring.ModelBundle` refuses to load an artifact whose feature schema
does not match the runtime `MODEL_FEATURE_NAMES`, and falls back to the transparent rules-only
scorer rather than crash.

At load time the bundle verifies a fast tree-walk inference path against sklearn's `predict_proba`
on a probe set and enables it only on exact agreement (`inference_path: fast_tree` on `/health`).

`joblib` files are pickles and therefore executable. Load only artifacts you built or that came from
a signed registry. Retrain with `make train`; the model card is `docs/MODEL_CARD.md`.
