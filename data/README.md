# Synthetic corpus

All identities, devices, SIMs, recipients, locations and labels are synthetic. Nothing here is
derived from real customers. See `docs/SYNTHETIC_DATA.md` for the generator design and its limits.

| File | Rows | Produced by | Purpose |
|---|---|---|---|
| `synthetic_accounts.csv` | 750 | `scripts/generate_synthetic.py` | Account personas |
| `synthetic_events.csv` | ~33.8k | `scripts/generate_synthetic.py` | Raw chronological events, sessions, precursors |
| `training_features.csv` | 30,000 | `scripts/generate_synthetic.py` via the production `FeatureEngine` | Model training rows (~0.81% takeover prevalence) |

The files are versioned (~29 MB) so evaluations are reproducible against a fixed corpus; the
model artifact records `training_data_sha256`. Regenerate with `make data`, then `make train` and
`make evidence` — the hashes will change and every quoted number must be re-checked.

`aegistwin.db` (the API's default runtime database) is created here at run time and is git-ignored.
