# AegisTwin v1.2 platform controls

Version 1.0 keeps the ten intelligence layers from v0.5 and adds the controls needed to operate them responsibly.

Version 1.1 adds an executable power/network contingency layer without changing the frozen held-out detector metrics.

Version 1.2 adds gateway-attested agent-terminal integrity, cross-customer campaign detection,
independent-victim reputation and reversible quarantine without changing the population-model feature schema.

| Control | Runtime behaviour | Failure boundary |
|---|---|---|
| Safe Learning Firewall | A provisionally safe current event waits 24 hours before it can update the profile. Fraud feedback revokes it and rebuilds the twin. | The prototype matures events in process; production needs a durable scheduler. |
| Campaign DNA | Privacy-reduced attack-stage signatures accumulate across distinct accounts within a tenant. At least three stages and a material attack stage are required. | No cross-tenant raw identity correlation. |
| Exact replay | Every decision stores event, feature, model, policy and cutoff digests. Replay verifies the immutable decision envelope. | It proves reproducibility of stored evidence, not correctness of the original inputs. |
| Transaction lifecycle | Created, authorized, held, released, settled and cancelled states use validated, idempotent transitions and an outbox event. | The demo outbox has no external settlement connector. |
| Recipient consortium | Original HMAC-token compatibility path; superseded in v1.3 by signed, rotating recipient/terminal/campaign sketches with revocation and outage cache. | VOPRF/PSI, HSM keys, governance and legal agreements are deployment responsibilities. |
| Analyst governance | Risk/value/confidence-prioritised cases, a deterministic random-audit sample, appeals, and dual approval for repeated recipient reports. | Identity provider integration is represented by role keys. |
| Policy governance | Threshold what-if simulation cannot mutate live policy. Policy version is bound into provenance. | Simulation uses recorded risk scores; production testing must replay raw events. |
| Model governance | Artifact, dataset and schema hashes plus a registry signature are exposed. PSI drift is sample gated. | The signature is a reference HMAC, not a hardware-backed production signature. |
| Privacy controls | Tenant ownership checks, HMAC identifiers, queued export/delete requests and conservative profile succession. | The prototype queues deletion so legal holds and audit retention can be checked first. |
| Operational controls | Rate limit, request-size cap, security headers, Prometheus text, SBOM, backup/restore proof and hardened container defaults. | SQLite remains a single-node prototype store. |
| Outage state controller | Fresh signed heartbeats select online, degraded, isolated or reconciling behaviour. | HMAC and simulated health sources must become workload identity and independent monitors. |
| Edge decision capsule | Expiring signed model/policy envelope supports bounded degraded operation. | Production needs hardware-backed signing and anti-rollback. |
| Store-and-forward recovery | Hash-chained outage journal, learning freeze, integrity gate, non-mutating re-score and zero automatic settlements. | Production needs encrypted replication, priority workers and ledger-owned idempotency. |
| Agent-terminal integrity | Attested causal cross-customer aggregates, compound campaign guard, tenant-bound reputation and three-victim quarantine. | Production needs signed registry assertions, distributed feature state, agent appeal/reinstatement and rural/urban cohort validation. |

The controls deliberately avoid two dangerous shortcuts: a high score is never treated as proof of guilt, and a single intelligence report never creates an automatic hard block.
