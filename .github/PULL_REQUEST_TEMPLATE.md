## What

<!-- One paragraph. Link the issue if there is one. -->

## Why

<!-- The problem this solves, or the evidence that motivated it. -->

## What could this make worse?

<!-- Fraud detection changes trade recall against customer friction. Say which way this moves and for whom
     (channel, cohort, cold-start profiles). "Nothing" is rarely the honest answer. -->

## Evidence

- [ ] `make check` passes (ruff, pytest with coverage gate, release smoke test, robustness gates)
- [ ] If `features.py`, `scoring.py`, `policy.py`, the generator or the model changed: `artifacts/` and
      `docs/EVALUATION.md` regenerated in this PR, and the quoted numbers in `README.md`, `docs/MODEL_CARD.md`
      and `submission/package_text/README_FIRST.md` updated
- [ ] New behaviour has a test that fails without the change
- [ ] `CHANGELOG.md` updated under *Unreleased*
- [ ] No real identifiers, personal data or secrets anywhere in the diff
