# Security policy

Report suspected vulnerabilities privately to the project maintainers. Do not include customer data, credentials, exploit payloads, or live banking identifiers in a public issue.

The prototype enforces role-separated keys, tenant ownership checks, request limits, security headers, HMAC-tokenised consortium identifiers, attested-evidence freshness, dual control for reputation escalation, safe-learning quarantine, exact decision replay, idempotent lifecycle transitions, and an independently signable audit-chain head.

Production deployment must replace static demonstration keys with short-lived workload identity and mTLS; use an encrypted managed database and queue; load only signed model artifacts; operate secrets through a managed vault; run independent penetration, privacy, fairness and resilience testing; and establish incident-response ownership. No prototype control is a certification or guarantee of fraud prevention.
