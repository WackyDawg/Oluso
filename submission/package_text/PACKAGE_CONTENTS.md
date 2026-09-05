# Package contents

| Item | Purpose |
|---|---|
| `AegisTwin_TrackA_Technical_Writeup.pdf` | Required four-page A4 technical submission |
| `AegisTwin_TrackA_Technical_Writeup.docx` | Editable source of the technical write-up |
| `AegisTwin_TrackA_Demo.mp4` | 36-second captioned working-prototype demo |
| `AegisTwin_TrackA_Code.zip` | Complete source, tests, model, synthetic data and documentation |
| `Documentation/` | Architecture, API, private fraud-sketch exchange, agent-terminal, outage, threat, model, data, evaluation and operational documentation |
| `Evidence/` | Raw evaluation, robustness, latency/load, coverage, SBOM, backup/restore and live proofs, including the fraud-sketch exchange |
| `CODE_LINK.md` | Captain-owned public repository link placeholder |
| `SUBMISSION_CHECKLIST.md` | Final captain actions and organizer deadlines |
| `SHA256SUMS.txt` | Integrity manifest for every top-level submission asset and evidence/documentation file |

The archive intentionally excludes virtual environments, Python caches, runtime databases, dashboard state and intermediate render frames. Packaging is blocked unless the inner source ZIP parses its own `.env.example`, imports the app and returns HTTP 200 from `/health` in a clean staging directory.
