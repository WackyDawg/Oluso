# Control traceability

| Risk | Preventive control | Detective/recovery control | Evidence |
|---|---|---|---|
| Profile poisoning | 24-hour learning quarantine | Feedback revocation and profile rebuild | `test_safe_learning_quarantine_maturation_and_delearning` |
| Replayed settlement command | Valid lifecycle state graph and idempotency key | Lifecycle history and outbox | `test_exact_replay_and_idempotent_transaction_lifecycle` |
| Coordinated low-signal attack | Three-stage campaign eligibility | Distinct-account campaign score | `test_campaign_guard_and_cross_account_propagation` |
| False consortium accusation | Two independent institution minimum | HMAC-scoped audit entry | `test_consortium_requires_independent_institutions` |
| Watchlist analyst error | Independent second approver | Appeals and audit chain | `test_feedback_dual_control_after_first_recipient_report` |
| Cross-tenant access | Tenant-bound account/event/decision queries | 404 isolation and audit role | `test_api_rbac_tenant_isolation_and_security_headers` |
| Unreproducible score | Model/policy/cutoff digests | Exact replay endpoint | replay test and `v1_platform_demo.json` |
| Unsafe threshold change | Non-mutating policy simulation | Version-bound decision provenance | governance test |
| Model drift | Sample-gated PSI | Explicit stable/watch/alert state | drift endpoint |
| Audit database alteration | SHA-256 chain | HMAC-signed externalisable head | audit tests and backup manifest |
| Forged outage declaration | Fresh HMAC heartbeat and admin role | Unique nonce and chained mode-change audit | `test_signed_heartbeat_replay_protection_and_capsule` |
| Missing intelligence mistaken for safety | Confidence multiplier and explicit missing sources | Safety-envelope action and analyst-visible reason | degraded-mode test and `outage_resilience.json` |
| Offline profile poisoning | All outage events are learning-excluded | Re-score after restored evidence | `test_degraded_mode_lowers_confidence_freezes_learning_and_uses_safety_envelope` |
| Offline journal alteration | Tenant-scoped SHA-256 store-and-forward chain | Reconciliation blocks on integrity failure | `test_offline_journal_detects_payload_tampering` |
| Duplicate recovery action | Pending-to-reconciled state and non-mutating re-score | Repeated run returns `already_reconciled` | isolated reconciliation test |
| Forged terminal assurance | Ignore unattested envelope and reject it outside agent channel | Zero agent evidence in decision envelope | `test_feedback_propagates_terminal_reputation_and_unattested_claim_is_ignored` |
| Cross-customer agent-terminal campaign | Causal diversity, recipient concentration and suspicious corroboration | Separate terminal summary, reason and analyst queue priority | `test_compromised_terminal_cross_customer_campaign_is_detected` |
| Busy legitimate agent false positive | Volume alone cannot activate the compound floor | Dedicated market-merchant hard negative | `test_busy_legitimate_agent_terminal_is_not_a_campaign` and evaluation cohort |
| One mistaken report quarantines agent | Independent-account progression and second approval | Decay, expiry, analyst status and audit record | `test_three_independent_confirmations_quarantine_terminal` |
| Terminal intelligence outage | Missing source lowers confidence, never risk | Journal, restored re-score and no auto-settlement | resilience tests plus `outage_resilience.json` |
| Cross-bank sketch impersonation/replay | Enrolled institution key, canonical signature, freshness and nonce | Reject conflicting report ID; audit every accepted report | `test_signature_tamper_nonce_replay_and_unknown_institution` |
| Private indicator disclosure | Epoch HMAC token and token-free API response | Shared-row privacy assertion and bounded retention | `test_private_tokens_independence_and_no_raw_storage` |
| False shared accusation | One bank/uncorroborated evidence is monitor-only | Issuer-signed revocation, decay and expiry | `test_action_ceiling_requires_local_corroboration` and `test_signed_outage_cache_and_revocation` |
| Consortium outage | Signed 24-hour cached aggregate with score/confidence discount | Invalid/expired cache ignored; source labelled | `test_signed_outage_cache_and_revocation` and `fraud_sketch_exchange.json` |
