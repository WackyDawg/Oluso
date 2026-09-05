# Machine-readable evidence

Every file here is produced by a script and is regenerable; none is edited by hand. They are
versioned so a reviewer can check the numbers quoted in the documentation without running anything.

| File | Producer | What it proves |
|---|---|---|
| `evaluation.json` | `scripts/evaluate_system.py` | Held-out operating points with bootstrap/Wilson intervals, component ablation, detection attribution, prevalence stress, cohorts |
| `robustness.json` | `scripts/evaluate_robustness.py` | Separability audit, account-disjoint generalisation, evidence-coverage leakage gate |
| `latency.json` | `scripts/benchmark_latency.py` | Warm sequential full-API latency |
| `concurrent_load.json` | `scripts/load_test.py` | Eight-worker SQLite stress with audit-chain validity |
| `adaptive_redteam.json` | `scripts/adaptive_attack_search.py` | Constrained adaptive-attacker search and disclosed evasion |
| `agent_terminal_demo.json` | `scripts/demo_agent_terminal.py` | Agent-terminal integrity scenarios |
| `fraud_sketch_exchange.json` | `scripts/demo_fraud_sketch_exchange.py` | Private multi-institution fraud-sketch exchange proof |
| `outage_resilience.json` | `scripts/demo_outage_resilience.py` | Degraded / isolated / reconciling drill |
| `v1_platform_demo.json`, `v5_feature_demo.json` | `scripts/demo_v1_platform.py`, `scripts/demo_v5_features.py` | Platform and intelligence-layer live proofs |
| `v1_platform_demo_backup.db` + `.manifest.json` | `scripts/backup_database.py` | Online backup, integrity check and restore proof |
| `coverage.json` | `pytest --cov` | Test coverage |
| `sbom.cdx.json` | `scripts/generate_sbom.py` | CycloneDX software bill of materials |

Runtime databases (`*.db` other than the backup) are scratch files and git-ignored.
Run `make evidence` after any change to features, scoring, policy, data or the model.
