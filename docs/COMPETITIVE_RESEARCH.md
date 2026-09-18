# Competitive Research: SIM-Swap Dataset Repository

Reviewed source: [sliit-msc-research/sim-swap-fraud-detection-model-dataset](https://github.com/sliit-msc-research/sim-swap-fraud-detection-model-dataset), inspected 24 August 2026.

## Useful ideas adopted through a clean-room implementation

The repository highlights a compact SIM-lifecycle signal family: SIM activation recency,
IMSI/ICCID change indicators, SIM-type change, repeat SIM changes in 30 days, previous-SIM
tenure, the time between SIM change and OTP use, and geographic separation between those
events. Oluso independently implements privacy-reduced versions of these concepts as an
optional `telco_assurance` object. It never needs the raw IMSI or ICCID. Values affect scoring
only when a trusted bank/telco gateway sets `gateway_attested=true`.

This makes the ideas especially useful for USSD and feature phones: server- and network-side
evidence can supplement transaction, recipient, velocity, interaction-rhythm, and account-history
signals even when device sensors do not exist.

## What was not reused, and why

- No rows, code, labels, or model artifacts were copied. The repository exposes no license.
- The repository currently contains two CSV files and a README, but no reproducible generator or
  evaluation pipeline.
- Both downloaded CSVs contain 100,000 rows, despite one filename stating 50,000.
- The positive label rate is approximately 73.9% in both files. That is not representative of rare
  live account takeover and would make ordinary accuracy or precision misleading.
- The README says the label is produced from a weighted combination of the same feature columns.
  Training and evaluating on those labels can reward recovery of the synthetic rule rather than
  generalization to independent fraud behaviour.

## Oluso's stronger research design

Oluso generates longitudinal account histories first, injects takeover sequences only after a
profile matures, derives features using the same production feature engine, prevents attack events
from contaminating the trusted baseline, and reserves the newest time window for testing. Fraud is
kept rare, hard legitimate cases are explicitly generated, and results report recall, false-positive
rate, precision, prevalence stress, channel cohorts, and known failure cases.
