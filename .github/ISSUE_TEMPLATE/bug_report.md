---
name: Bug report
about: Something behaves differently from the documentation or tests
labels: bug
---

**What happened**

**What you expected**

**Minimal reproduction**

```bash
# commands, request payload (synthetic data only), or failing test
```

**Environment**

- OS / Python version:
- Commit or version (`GET /v1/model` → `version`, `artifact_hash`):
- `inference_path` reported by `/health`:

**Decision context (if scoring-related)**

Attach the `decision_id`, the `reasons` list and the `fusion_*` fields from `feature_snapshot`.
Never attach real customer data.
