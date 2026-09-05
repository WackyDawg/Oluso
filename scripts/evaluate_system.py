from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

from aegistwin.evaluation import (
    ablation_table,
    bootstrap_operating_point,
    detection_attribution,
    fusion_breakdowns,
)
from aegistwin.features import FEATURE_NAMES, MODEL_FEATURE_NAMES
from aegistwin.policy import POLICY_THRESHOLDS as LADDER
from aegistwin.scoring import AnomalyScorer

POLICY_THRESHOLDS = {
    "Monitor or stronger": LADDER["monitor"],
    "Customer confirmation or stronger": LADDER["confirm"],
    "Settlement delay or hold": LADDER["delay"],
    "Two-hour hold and review": LADDER["hold"],
}
CHALLENGE_POINT = "Customer confirmation or stronger"


def operating_point(labels: np.ndarray, scores: np.ndarray, threshold: float) -> dict[str, Any]:
    predictions = scores >= threshold
    positives = int((labels == 1).sum())
    negatives = int((labels == 0).sum())
    true_positives = int((predictions & (labels == 1)).sum())
    false_positives = int((predictions & (labels == 0)).sum())
    return {
        "threshold": threshold,
        "recall": round(float(recall_score(labels, predictions, zero_division=0)), 6),
        "precision": round(float(precision_score(labels, predictions, zero_division=0)), 6),
        "false_positive_rate": round(false_positives / max(1, negatives), 6),
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": positives - true_positives,
        "normal_events": negatives,
        "takeover_events": positives,
    }


def cohort_rates(
    frame: pd.DataFrame,
    labels: np.ndarray,
    scores: np.ndarray,
    column: str,
    threshold: float,
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    predictions = scores >= threshold
    for value, cohort in frame.groupby(column):
        positions = frame.index.get_indexer(cohort.index)
        cohort_labels = labels[positions]
        cohort_predictions = predictions[positions]
        positives = int((cohort_labels == 1).sum())
        negatives = int((cohort_labels == 0).sum())
        output[str(value)] = {
            "samples": len(cohort),
            "takeovers": positives,
            "recall": (
                round(float(cohort_predictions[cohort_labels == 1].mean()), 6)
                if positives
                else None
            ),
            "false_positive_rate": (
                round(float(cohort_predictions[cohort_labels == 0].mean()), 6)
                if negatives
                else None
            ),
        }
    return output


def prevalence_stress(recall: float, fpr: float) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for prevalence in (0.001, 0.005, 0.01):
        true_alert_rate = recall * prevalence
        false_alert_rate = fpr * (1.0 - prevalence)
        output[f"{prevalence:.3%}"] = {
            "projected_precision": round(
                true_alert_rate / max(true_alert_rate + false_alert_rate, 1e-12), 6
            ),
            "projected_alerts_per_10000": round(
                10_000 * (true_alert_rate + false_alert_rate), 2
            ),
            "projected_false_alerts_per_10000": round(10_000 * false_alert_rate, 2),
        }
    return output


def expected_calibration_error(
    labels: np.ndarray, probabilities: np.ndarray, bins: int = 10
) -> float:
    total = len(labels)
    error = 0.0
    for lower in np.linspace(0.0, 1.0, bins, endpoint=False):
        upper = lower + 1.0 / bins
        included = (probabilities >= lower) & (
            probabilities <= upper if upper >= 1.0 else probabilities < upper
        )
        if not included.any():
            continue
        confidence = float(probabilities[included].mean())
        observed = float(labels[included].mean())
        error += float(included.sum()) / total * abs(confidence - observed)
    return round(error, 6)


def separation_summary(labels: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    normal = scores[labels == 0]
    attacks = scores[labels == 1]
    return {
        "normal_max": round(float(normal.max()), 6),
        "takeover_min": round(float(attacks.min()), 6),
        "perfect_ranking_gap": bool(float(attacks.min()) > float(normal.max())),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# End-to-End Evaluation",
        "",
        "## Release assurance, robustness and platform verification",
        "",
        (
            "The full automated suite (see `README.md` for the current test count and coverage gate) "
            "runs on every change. The executable outage drill "
            "moves through degraded, isolated, reconciling and online states; validates the signed edge "
            "capsule; freezes profile learning; detects deliberate journal tampering; and performs no "
            "duplicate lifecycle action or automatic settlement. The agent-terminal proof allows a busy "
            "legitimate endpoint, delays a compromised cross-customer campaign, quarantines after three "
            "independent victims and ignores a forged unattested claim. See `artifacts/outage_resilience.json` "
            "and `artifacts/agent_terminal_demo.json`. Signed private-exchange evidence, action ceilings, "
            "revocation and outage cache are separately recorded in `artifacts/fraud_sketch_exchange.json`."
        ),
        "",
        (
            "Warm full-API and concurrent SQLite results are kept in `artifacts/latency.json` and "
            "`artifacts/concurrent_load.json`. These laptop measurements prove executable paths, not a "
            "bank availability or production-scale claim."
        ),
        "",
        "This report evaluates the exact live fusion and policy thresholds, not only the population model.",
        "All results use held-out synthetic Nigerian sessions and demonstrate pipeline behaviour, not production accuracy.",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Model: `{report['model_version']}`",
        f"- Test events: `{report['test_samples']}`",
        f"- Takeover events: `{report['takeover_samples']}`",
        f"- Synthetic takeover prevalence: `{report['synthetic_prevalence']:.3%}`",
        f"- Model-only ROC-AUC / PR-AUC: `{report['model_only_roc_auc']:.4f}` / `{report['model_only_pr_auc']:.4f}`",
        f"- Fused ROC-AUC: `{report['fused_roc_auc']:.4f}`",
        f"- Fused PR-AUC: `{report['fused_pr_auc']:.4f}`",
        f"- Model Brier / expected calibration error: `{report['model_calibration']['brier_score']:.4f}` / `{report['model_calibration']['expected_calibration_error']:.4f}`",
        "",
        "## Live policy operating points",
        "",
        "| Response threshold | Recall | Precision | False-positive rate | TP | FP | FN |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in report["operating_points"].items():
        lines.append(
            f"| {name} | {result['recall']:.2%} | {result['precision']:.2%} | "
            f"{result['false_positive_rate']:.2%} | {result['true_positives']} | "
            f"{result['false_positives']} | {result['false_negatives']} |"
        )

    uncertainty = report["uncertainty"]
    lines.extend(
        [
            "",
            "## Uncertainty of the headline numbers",
            "",
            (
                f"With only {report['takeover_samples']} held-out takeovers, point estimates are wide. "
                f"Intervals are {uncertainty['confidence']:.0%} stratified percentile bootstrap "
                f"({uncertainty['resamples']} resamples, seed {uncertainty['seed']}); Wilson intervals "
                "for the binomial rates are shown alongside. Quote the interval, not the point."
            ),
            "",
            "| Response threshold | Recall [CI] | Recall (Wilson) | FPR [CI] | FPR (Wilson) | Precision [CI] |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for name, result in uncertainty["operating_points"].items():
        metrics = result["metrics"]
        recall, fpr, precision = metrics["recall"], metrics["false_positive_rate"], metrics["precision"]
        lines.append(
            f"| {name} | {recall['point']:.2%} [{recall['ci_lower']:.2%}, {recall['ci_upper']:.2%}] | "
            f"[{recall['wilson'][0]:.2%}, {recall['wilson'][1]:.2%}] | "
            f"{fpr['point']:.3%} [{fpr['ci_lower']:.3%}, {fpr['ci_upper']:.3%}] | "
            f"[{fpr['wilson'][0]:.3%}, {fpr['wilson'][1]:.3%}] | "
            f"{precision['point']:.2%} [{precision['ci_lower']:.2%}, {precision['ci_upper']:.2%}] |"
        )
    auc = uncertainty["fused_roc_auc"]
    model_auc = uncertainty["model_only_roc_auc"]
    lines.extend(
        [
            "",
            f"- Fused ROC-AUC: `{auc['point']:.4f}` [{auc['ci_lower']:.4f}, {auc['ci_upper']:.4f}]",
            f"- Model-only ROC-AUC: `{model_auc['point']:.4f}` [{model_auc['ci_lower']:.4f}, {model_auc['ci_upper']:.4f}]",
        ]
    )

    ablation = report["component_ablation"]
    lines.extend(
        [
            "",
            "## Component ablation at the customer-confirmation threshold",
            "",
            (
                "The live score is `max(blend, security_floor)` where the blend mixes the calibrated "
                "population model with the transparent behavioural scorer. Each row scores the held-out "
                "set with one component alone so it is clear how much detection is learned versus rule-based."
            ),
            "",
            "| Component | Recall | Precision | FPR | TP | FP | ROC-AUC |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for name, result in ablation.items():
        auc_text = "n/a" if result["roc_auc"] is None else f"{result['roc_auc']:.4f}"
        lines.append(
            f"| `{name}` | {result['recall']:.2%} | {result['precision']:.2%} | "
            f"{result['false_positive_rate']:.3%} | {result['true_positives']} | "
            f"{result['false_positives']} | {auc_text} |"
        )

    attribution = report["detection_attribution"]
    tp = attribution["true_positives"]
    fp = attribution["false_positives"]
    lines.extend(
        [
            "",
            "## Detection attribution",
            "",
            (
                "For every alert at the customer-confirmation threshold: did the model/anomaly blend "
                "reach the threshold on its own, or did a named security floor lift it there?"
            ),
            "",
            "| Outcome | Blend alone | Floor required | Both | Total |",
            "|---|---:|---:|---:|---:|",
            f"| True positives | {tp['blend_alone']} | {tp['floor_required']} | {tp['both']} | {tp['total']} |",
            f"| False positives | {fp['blend_alone']} | {fp['floor_required']} | {fp['both']} | {fp['total']} |",
            "",
            (
                f"- Share of true positives that needed a floor: **{_pct(tp['floor_required_share'])}**; "
                f"caught by the blend alone: **{_pct(tp['blend_alone_share'])}**."
            ),
        ]
    )
    if attribution["floor_codes_among_true_positives"]:
        codes = ", ".join(
            f"`{code}` ({count})"
            for code, count in attribution["floor_codes_among_true_positives"].items()
        )
        lines.append(f"- Floors present among floor-level true positives: {codes}.")
    if attribution["floor_codes_among_false_positives"]:
        codes = ", ".join(
            f"`{code}` ({count})"
            for code, count in attribution["floor_codes_among_false_positives"].items()
        )
        lines.append(f"- Floors present among floor-level false positives: {codes}.")

    lines.extend(
        [
            "",
            "## Rare-fraud prevalence stress test",
            "",
            "Projection uses the customer-confirmation operating point while changing only prevalence.",
            "",
            "| Assumed takeover prevalence | Projected precision | Alerts / 10,000 | False alerts / 10,000 |",
            "|---:|---:|---:|---:|",
        ]
    )
    for prevalence, result in report["prevalence_stress"].items():
        lines.append(
            f"| {prevalence} | {result['projected_precision']:.2%} | "
            f"{result['projected_alerts_per_10000']:.2f} | "
            f"{result['projected_false_alerts_per_10000']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Customer-protection hard negatives",
            "",
            "| Legitimate scenario | Events | Customer-confirmation rate |",
            "|---|---:|---:|",
        ]
    )
    for scenario, result in report["hard_negative_intervention"].items():
        lines.append(
            f"| {scenario.replace('_', ' ').title()} | {result['events']} | "
            f"{result['intervention_rate']:.2%} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                f"The challenge threshold begins at customer confirmation (`{LADDER['confirm']}`). Lower-risk events may be "
                "monitored without interrupting the customer. Higher-risk events receive reversible delays or "
                "holds. Neither model-only nor fused ranking is perfect after removing post-label reputation "
                "and event-type shortcuts and adding groomed-recipient attacks plus legitimate behavioural "
                "lookalikes. The account-disjoint result, separability audit and evidence-coverage leakage "
                "audit are in `artifacts/robustness.json`."
            ),
            "",
            (
                "The synthetic generator, the transparent scorer and the security floors were designed by the "
                "same team against the same threat model, so the evaluation measures agreement with that model "
                "rather than real-world fraud. The ablation and attribution tables above exist so a reader can "
                "see exactly how much of the result comes from learned behaviour versus encoded rules."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the complete AegisTwin runtime policy")
    parser.add_argument("--input", type=Path, default=Path("data/training_features.csv"))
    parser.add_argument("--model", type=Path, default=Path("models/ato_model.joblib"))
    parser.add_argument("--json-output", type=Path, default=Path("artifacts/evaluation.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("docs/EVALUATION.md"))
    parser.add_argument("--bootstrap-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    frame = pd.read_csv(args.input).sort_values("event_time").reset_index(drop=True)
    test = frame.iloc[int(len(frame) * 0.82) :].copy()
    artifact = joblib.load(args.model)
    artifact_features = list(artifact.get("feature_names", []))
    if artifact_features != MODEL_FEATURE_NAMES:
        raise ValueError("model feature schema does not match the evaluation schema")
    probabilities = artifact["model"].predict_proba(test[artifact_features])[:, 1]
    scorer = AnomalyScorer()
    feature_rows = [
        {name: float(row[name]) for name in FEATURE_NAMES} for _, row in test.iterrows()
    ]
    anomaly_scores = np.asarray([scorer.score(features).score for features in feature_rows])
    breakdowns = fusion_breakdowns(probabilities, anomaly_scores, feature_rows)
    fused = np.asarray([item.fused_score for item in breakdowns])
    labels = test["is_takeover"].to_numpy()
    operating_points = {
        name: operating_point(labels, fused, threshold)
        for name, threshold in POLICY_THRESHOLDS.items()
    }
    challenge_threshold = POLICY_THRESHOLDS[CHALLENGE_POINT]
    challenge_result = operating_points[CHALLENGE_POINT]
    transfer_mask = test["is_transfer"].to_numpy() >= 0.5
    development = frame.iloc[: int(len(frame) * 0.82)]

    hard_negative_intervention: dict[str, dict[str, Any]] = {}
    for scenario, cohort in test[
        (test["is_takeover"] == 0) & (test["scenario"] != "legitimate")
    ].groupby("scenario"):
        positions = test.index.get_indexer(cohort.index)
        hard_negative_intervention[str(scenario)] = {
            "events": len(cohort),
            "intervention_rate": round(float((fused[positions] >= challenge_threshold).mean()), 6),
        }

    uncertainty_points = {
        name: bootstrap_operating_point(
            labels, fused, threshold, resamples=args.bootstrap_resamples, seed=args.seed
        )
        for name, threshold in POLICY_THRESHOLDS.items()
    }
    model_uncertainty = bootstrap_operating_point(
        labels,
        probabilities,
        float(artifact.get("decision_threshold", 0.5)),
        resamples=args.bootstrap_resamples,
        seed=args.seed,
    )
    uncertainty = {
        "method": "stratified percentile bootstrap",
        "resamples": args.bootstrap_resamples,
        "seed": args.seed,
        "confidence": 0.95,
        "operating_points": uncertainty_points,
        "fused_roc_auc": uncertainty_points[CHALLENGE_POINT]["metrics"]["roc_auc"],
        "model_only_roc_auc": model_uncertainty["metrics"]["roc_auc"],
    }

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model_version": artifact.get("version", "unknown"),
        "model_artifact_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
        "training_data_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "test_samples": len(test),
        "takeover_samples": int(labels.sum()),
        "synthetic_prevalence": float(labels.mean()),
        "fused_roc_auc": round(float(roc_auc_score(labels, fused)), 6),
        "fused_pr_auc": round(float(average_precision_score(labels, fused)), 6),
        "model_only_roc_auc": round(float(roc_auc_score(labels, probabilities)), 6),
        "model_only_pr_auc": round(float(average_precision_score(labels, probabilities)), 6),
        "model_calibration": {
            "brier_score": round(float(brier_score_loss(labels, probabilities)), 6),
            "expected_calibration_error": expected_calibration_error(labels, probabilities),
        },
        "score_separation": {
            "model_only": separation_summary(labels, probabilities),
            "fused": separation_summary(labels, fused),
        },
        "uncertainty": uncertainty,
        "component_ablation": ablation_table(labels, breakdowns, challenge_threshold),
        "detection_attribution": detection_attribution(labels, breakdowns, challenge_threshold),
        "transfer_only": {
            "samples": int(transfer_mask.sum()),
            "takeover_samples": int(labels[transfer_mask].sum()),
            "model_only_roc_auc": round(
                float(roc_auc_score(labels[transfer_mask], probabilities[transfer_mask])), 6
            ),
            "fused_roc_auc": round(
                float(roc_auc_score(labels[transfer_mask], fused[transfer_mask])), 6
            ),
            "customer_confirmation": operating_point(
                labels[transfer_mask], fused[transfer_mask], challenge_threshold
            ),
        },
        "chronological_split": {
            "development_events": len(development),
            "test_events": len(test),
            "development_accounts": int(development["account_id"].nunique()),
            "test_accounts": int(test["account_id"].nunique()),
            "overlapping_accounts": len(
                set(development["account_id"]) & set(test["account_id"])
            ),
            "purpose": "within-customer future-event evaluation for personalised behavioural twins",
        },
        "operating_points": operating_points,
        "prevalence_stress": prevalence_stress(
            float(challenge_result["recall"]),
            float(challenge_result["false_positive_rate"]),
        ),
        "channel_cohorts": cohort_rates(
            test, labels, fused, "channel", challenge_threshold
        ),
        "scenario_cohorts": cohort_rates(
            test, labels, fused, "scenario", challenge_threshold
        ),
        "hard_negative_intervention": hard_negative_intervention,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report["operating_points"], indent=2))
    print(json.dumps(report["component_ablation"], indent=2))
    print(json.dumps(report["detection_attribution"], indent=2))
    print(f"wrote={args.json_output}")
    print(f"wrote={args.markdown_output}")


if __name__ == "__main__":
    main()
