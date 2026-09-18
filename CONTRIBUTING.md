# Contributing to Oluso

Thanks for helping. This document covers local setup, the checks every change must pass, and
how the evidence and submission artefacts are regenerated so nobody has to reverse-engineer it.

## Repository layout

```text
.
├── src/oluso/           Library: API, features, scoring, policy, storage, resilience, fraud-sketch
├── tests/               pytest suite (CI gate: 85% line coverage)
├── scripts/             Data generation, training, evaluation, benchmarks, demos, release smoke test
├── tools/               Submission builders: write-up (DOCX), demo video (MP4), final package
├── dashboard/           Streamlit investigator console
├── docs/                Architecture, model card, governance, threat model, runbooks (single source)
├── artifacts/           Machine-readable evidence produced by scripts/ (versioned, regenerable)
├── data/                Synthetic corpus (versioned; regenerate with scripts/generate_synthetic.py)
├── models/              Versioned model artifact + hashes (regenerate with scripts/train_model.py)
├── submission/          Hackathon deliverables: cover text, report, demo; dist/ is generated
├── app.py               uvicorn entry point (`uvicorn app:app`)
└── .github/             CI (ruff, pytest+coverage, smoke, robustness gates, bandit, pip-audit, SBOM), CodeQL, Dependabot
```

Rule of thumb: **`docs/` and `artifacts/` are the only copies.** The judge-facing `Documentation/`
and `Evidence/` folders are produced by `tools/package_submission.py` into `submission/dist/`
and are never edited by hand.

## Local setup

Python 3.11+ (CI uses 3.12; 3.14 is known to work).

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e '.[dev,dashboard]'
cp .env.example .env                                # never commit .env
```

Or with [uv](https://docs.astral.sh/uv/): `uv sync --extra dev --extra dashboard` and prefix
commands with `uv run`.

## Everyday commands

| Task | `make` | Direct |
|---|---|---|
| Lint | `make lint` | `ruff check .` |
| Tests | `make test` | `pytest` |
| Tests + coverage gate | `make coverage` | `pytest --cov=oluso --cov-fail-under=85` |
| Release smoke test | `make smoke` | `python scripts/release_smoke_test.py .` |
| Everything CI runs | `make check` | the three above + `python scripts/evaluate_robustness.py` |
| API | `make serve` | `uvicorn app:app --reload` |
| Dashboard | `make dashboard` | `streamlit run dashboard/app.py` |

Windows without GNU make: use the "Direct" column.

## Changing the model, features or policy

Any change to `features.py`, `scoring.py`, `policy.py`, the generator or the model must
regenerate evidence so the documentation never drifts from the code:

```bash
make data          # only if the generator changed
make train         # only if features/data changed; bumps the artifact hash
make evaluate      # artifacts/evaluation.json + docs/EVALUATION.md
make robustness    # artifacts/robustness.json (fails on shortcut features or coverage leakage)
make bench load    # latency evidence; run load with the DB off OneDrive/Dropbox
```

Then update the numbers quoted in `README.md`, `docs/MODEL_CARD.md`, `docs/OPERATIONS_RUNBOOK.md`
and `submission/package_text/README_FIRST.md`. Quote intervals, not points — the held-out set has
44 takeovers.

Constants that govern behaviour live in exactly one place each:

- `oluso.policy.POLICY_THRESHOLDS` — response ladder
- `oluso.scoring.SECURITY_FLOOR_RULES` and the `MODEL_WEIGHT_*` constants — fusion
- `oluso.features.MODEL_EXCLUDED_FEATURES` — what the population model may *not* see

Add a floor by appending a `SecurityFloorRule`; it is automatically attributed in evaluation
output and in per-decision `SECURITY_FLOOR_APPLIED` reasons.

## Code conventions

- `ruff` is the formatter and linter (line length 110, target py311). No other tooling.
- Type hints everywhere; `from __future__ import annotations` at the top of each module.
- No network calls, real identifiers or personal data in tests or fixtures. Everything is synthetic.
- Tests live in `tests/` mirroring module names; new behaviour needs a test that would fail without it.
- Keep scripts idempotent and path-relative to the repository root (they are run from the root).

## Pull requests

1. Branch from `main`; one logical change per PR.
2. `make check` passes locally.
3. If evidence changed, commit the regenerated `artifacts/` and `docs/EVALUATION.md` in the same PR
   and say what moved and why.
4. Update `CHANGELOG.md` under *Unreleased*.
5. Fill in the PR template — in particular the "what could this make worse?" section.

## Building the submission package

```bash
make writeup      # DOCX from current artifacts; export the PDF manually and review the 4-page limit
make demo-video   # MP4 + demo_results.json (requires ffmpeg on PATH)
make package      # submission/dist/Oluso_TrackA_Final.zip with checksums; runs the smoke test
```

`submission/package_text/CODE_LINK.md` must point at the public repository before upload.

## Security

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md). Do not open public issues for them.
