# Operations runbook

## Normal checks

1. Confirm `/health` is `ok` and the audit chain is valid.
2. Check `/v1/observability` for scoring p95/p99 and action spikes.
3. Review high-priority cases and random-audit samples.
4. Check `/v1/governance/drift` only when `minimum_sample_met` is true; act on `retraining_recommended` and its `reasons` (score PSI, per-feature PSI, action-mix shift, mixed model versions) through the governed promotion path, never by auto-retraining.
5. Inspect outbox backlog and consumer acknowledgements in the production queue.

## Suspected compromise

Rotate affected credentials, block the integration identity, preserve logs and database snapshots, verify and externally anchor the last good audit head, compare replay digests, disable model promotion, move high-risk settlement states to reversible hold under approved authority, and notify the incident owner. Do not delete evidence during containment.

## Suspected agent-terminal compromise

1. Use the analyst-only terminal status endpoint and preserve the tokenised reference, contributing decisions, approval identities and audit head.
2. Confirm that the source events carried trusted gateway attestation; do not act on a customer-supplied terminal claim.
3. One affected account remains monitoring only. Elevation after a first report requires an independent second approver, and quarantine requires three distinct affected accounts.
4. Quarantine is reversible: stop new terminal-originated settlement instructions under the bank's approved authority, preserve customer access through alternate official channels and open an agent-owner appeal/investigation case.
5. Check the associated recipients and customers for loss or recovery activity without treating terminal linkage as proof of guilt.
6. Reinstate only through a documented dual-control process after credential rotation, terminal inspection and signed registry update. Record the decision in the audit chain.

## Power or network outage

1. Confirm the controller mode and unavailable sources through `/v1/resilience/status`; never accept an outage flag from a customer device.
2. In `degraded`, verify the signed capsule remains valid, monitor ordinary known-recipient activity, and use trusted confirmation for unusual payments.
3. In `isolated`, do not represent a payment as settled. Give the customer the `OFF-...` reference and retain the instruction in a held lifecycle state.
4. Watch offline queue depth, oldest event, capsule expiry and journal integrity. Freeze profile learning for all outage events.
5. When dependencies return, enter `reconciling`; verify the journal before processing any event.
6. Re-score pending events in bounded batches. Record score changes, send elevated changes to review, and perform no automatic settlement.
7. Require zero duplicate lifecycle actions before returning to `online`. Escalate any journal-integrity failure and preserve the database snapshot.

Run `python scripts/demo_outage_resilience.py` during release verification. Production owners must define and test bank-approved RTO, RPO, maximum capsule age, customer communication and alternate-site responsibilities.

## Rollback

Roll back policy separately from the model. Re-run the policy simulation over a frozen causal dataset, record the approving analyst and policy owner, deploy the prior signed version, and verify a known replay fixture. Model rollback must also verify artifact, data and schema hashes.

## Backup and restore

`scripts/backup_database.py` uses the SQLite online-backup API, runs `PRAGMA integrity_check`, hashes the result and emits a manifest. The included manifest proves the packaged prototype backup restored cleanly; production recovery objectives require recurring encrypted off-host backups and timed restoration exercises.

## Capacity

The warm sequential prototype benchmark is 32.5 ms p50, 45.8 ms p95 and 183.5 ms p99 over 100 requests. After eight explicit warm-up requests, the eight-worker SQLite stress completed 100/100 measured requests at 22.6 requests/s with 477.9 ms p99 and a 529.1 ms maximum. `/health` and `/v1/model` report `inference_path`; `fast_tree` is expected, and `sklearn` means the fast path failed its load-time self-check and the slower reference path is active. Per-request latency grows with the length of the account history that feature extraction scans (bounded by `ATO_MAX_HISTORY_EVENTS`, default 2,000); a 300-request run against one account moved p50 from 32 ms to 44 ms and p99 to 219 ms, so size that bound and the profile lookback window against the latency budget rather than assuming the 30-event benchmark figure. Cold start is excluded and concurrent margin is small; production still requires a concurrent transactional store, durable feature stream and distributed cold/warm load evidence before claiming scale.

Before packaging, run `python scripts/release_smoke_test.py .`. After packaging, run the same command against the inner source ZIP. The script stages a clean copy, parses the checked-in `.env.example`, imports the application and requires `/health` to return 200. A failure blocks release.
