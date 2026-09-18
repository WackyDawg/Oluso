# ICSC Submission Guide — Oluso Track A

## Required actions

1. Confirm the team's official name and rename the outer archive if it is not `Oluso_TrackA.zip`.
2. Submit the Track A selection form by **31 August 2026**:
   <https://forms.cloud.microsoft/r/xsk558qRQE>
3. Publish the included source to the team's code host and replace the placeholder in `CODE_LINK.md`.
4. Watch the MP4 and open the PDF once on the submission computer.
5. Upload the outer archive by **21 September 2026 at 11:59 PM**:
   <https://nitdanigeria-my.sharepoint.com/:f:/g/personal/sabdulrazaq_nitda_gov_ng/IgD_onAWwb4tS7LEbOQ3LwToAfOU34gkz8YgiChABqi5Hho>

## Building the package

Deliverables live under `submission/` (see `submission/README.md`). `make writeup`, `make demo-video` and `make package` regenerate the write-up, demo and the final `submission/dist/Oluso_TrackA_Final.zip`; the package tool copies `docs/` to `Documentation/`, `artifacts/` to `Evidence/`, zips the source, runs the release smoke test and writes `SHA256SUMS.txt`.

## Package contents

- A four-page technical write-up in PDF and editable DOCX.
- A captioned MP4 generated from a real local scoring run.
- A clean source-code ZIP with the model, synthetic data, evaluation evidence, 64 tests, and README.
- Complete Markdown documentation, including OlusoMesh private exchange, all intelligence lenses, outage safety and the adaptive red-team report.
- Machine-readable evaluation, robustness, latency, adaptive-search, platform, outage-resilience, agent-terminal, fraud-sketch and demo results, checksums, and this checklist.

No real personal data is included. The model is a prototype trained and tested only on synthetic data.
