# Oluso Track A — final submission

This is the self-contained ICSC Universities Category Track A package for **Spotting Account Takeover From Behaviour**.

Start with:

1. `Oluso_TrackA_Technical_Writeup.pdf` — the required four-page technical write-up.
2. `Oluso_TrackA_Demo.mp4` — a 36-second captioned demonstration generated from actual local service runs.
3. `Oluso_TrackA_Code.zip` — the complete runnable source, synthetic datasets, model, tests and documentation.
4. `Evidence/` — machine-readable evaluation, latency, load, adaptive-attacker, private fraud-sketch, agent-terminal, outage, governance, coverage, SBOM and restore proof.

## Final measured prototype evidence

- Customer-confirmation recall: **40/44 held-out takeovers (90.91%)**.
- False-positive rate at that threshold: **2/5,356 normal events (0.0373%)**.
- Model-only/fused ROC-AUC: **0.9729 / 0.9611**; perfect ranking is now a failing release condition.
- Zero-overlap account test: **83.33% recall and 0.1007% FPR** on 150 unseen accounts.
- Warm full-API latency: **32.5 ms p50 / 45.8 ms p95 / 183.5 ms p99** over 100 requests (two tail requests; the rest under 50 ms).
- Warmed concurrent SQLite stress: **100/100 successes; 22.6 requests/s; 477.9 ms p99; 529.1 ms maximum** with eight workers.
- Both benchmarks were re-measured on one laptop after replacing per-call SQLite connections with a pool and adding a verified fast inference path for the calibrated forest (identical probabilities to 1e-6). On that laptop the same code path went from 402 ms to 28 ms per warm request and from 1.5 to 22.6 requests/s under eight workers; no model, threshold or metric changed.
- Private exchange: **two independent institutions produced 0.726 shared risk; shared evidence alone remained monitor-only; local corroboration permitted a reversible delay**.
- Automated validation: **64 tests; 91% line coverage; lint passed; packaged startup smoke passed**.
- Uncertainty is reported, not hidden: customer-confirmation recall is 90.91% with a 95% bootstrap interval of **[81.8%, 97.7%]** (Wilson [78.8%, 96.4%]); FPR 0.037% **[0.000%, 0.093%]**.
- Component ablation shows the calibrated model alone reaches the same 40/44 at 0.48; security floors alone reach 32/44 with zero false alerts, and **no true positive depended on a floor**.

All identities, events, locations and labels are synthetic. These results prove the designed prototype pipeline and scenarios; they are not claims of real-bank accuracy or production readiness. At the main threshold, all three held-out low-and-slow attacks and one of four remote-control USSD attacks are missed; the small cohorts and every miss are retained in the evidence.

The fraud-sketch exchange is an honest privacy-reduced prototype: shared storage contains rotating tokens, coarse evidence and expiry rather than raw identifiers. A production pilot still requires VOPRF/PSI or secure aggregation, HSM-backed keys, independent security review and formal multi-bank governance.

The only incomplete submission item is the public code URL in `CODE_LINK.md`, which the team captain must replace after publishing the included source.
