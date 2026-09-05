# Privacy and compliance design

AegisTwin uses synthetic data only. It does not require raw IMSI, ICCID, contact lists, message text, call audio or screen contents. Coercion signals are consented, device-attested summaries. AegisMesh recipient, attested-terminal and campaign indicators use epoch-scoped HMAC tokens; institutions are separately tokenised. Shared tables exclude source identifiers and customer/transaction histories.

The v1.3 exchange is described as privacy-reduced, not anonymous. A prototype operator holding the token key could test guesses from a small identifier space. Production requires VOPRF/PSI or secure aggregation where appropriate, HSM-held rotation, institution identity, separation of duties, minimised query logs, formal participation agreements, correction/appeal handling and privacy testing. Signed shared capsules expire within 24 hours and are discounted during outages.

Data minimisation choices include masked trusted contacts, coarse IP prefixes, optional location, compact behavioural aggregates and evidence-coverage flags instead of fabricated values. A production privacy review should define purpose, lawful basis, minimisation, retention, access, customer notice, cross-border transfer, automated-decision safeguards and incident reporting under applicable Nigerian requirements.

Export and delete requests enter an audited queue. Deletion is not executed immediately because fraud evidence, appeals and legal holds may impose competing obligations. The production worker must resolve those obligations, delete or anonymise eligible data, preserve only authorised audit material and produce a completion receipt.

Profile succession after a verified device or SIM replacement requires two independent trusted confirmations. The old profile remains monitoring context while a new profile learns through quarantine; it is not blindly copied to a possibly compromised identity.
