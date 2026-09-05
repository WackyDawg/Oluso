# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow SemVer.

## [Unreleased]

### Added
- `aegistwin.evaluation`: Wilson and stratified-bootstrap intervals, component ablation,
  detection attribution and an evidence-coverage leakage audit; wired into
  `scripts/evaluate_system.py` and `scripts/evaluate_robustness.py` (new CI gate at 0.75 separation AUC).
- Named `SecurityFloorRule` table and `fuse_scores_detailed()`; every decision records which floors
  fired (`SECURITY_FLOOR_APPLIED` reason, `fusion_*` snapshot fields).
- `POLICY_THRESHOLDS` as the single source for the response ladder.
- Reference-window drift report: score PSI, per-feature PSI, action-mix shift, model-version scope and a
  `retraining_recommended` flag (recommends only; never retrains).
- Verified fast inference path for the calibrated forest (`FastCalibratedForest`), enabled only when it
  reproduces sklearn `predict_proba` to 1e-6 on a probe set; `inference_path` exposed on `/health` and `/v1/model`.
- SQLite connection pool, `(tenant_id, occurred_at)` index for the recipient-graph window scan, and
  app-lifespan shutdown that releases connections.
- `--database` flag on `scripts/load_test.py` so timings are not distorted by synced folders.
- Repository scaffolding: `Makefile`, `CONTRIBUTING.md`, `.gitignore`, `.gitattributes`, PR/issue templates,
  folder READMEs; hackathon deliverables consolidated under `submission/`.

### Changed
- Warm request latency ~402 ms → ~28 ms and 8-worker throughput 1.5 → 22.6 req/s on the reference laptop,
  with no change to any probability, threshold or metric.
- `tools/package_v13.py` → `tools/package_submission.py`, reading from `submission/` and writing to
  `submission/dist/`.
- Documentation now quotes intervals alongside point estimates and states that no true positive on the
  held-out corpus depended on a security floor.

### Fixed
- Unclosed SQLite connections (bootstrap connection, a test using the bare `sqlite3` context manager).
- Benchmark script teardown on Windows.

## [1.4.0] - 2026-08-30

- Release assurance: canonical JSON environment lists, extracted-package smoke test, honest-model
  evaluation (perfect synthetic ranking is a failing condition), account-disjoint evaluation,
  Brier/ECE reporting, groomed-recipient attacks and legitimate lookalikes in the corpus.
- See `README.md` for the v1.0–v1.3 feature history (platform, intelligence layers, agent-terminal
  integrity, outage resilience, private fraud-sketch exchange).
